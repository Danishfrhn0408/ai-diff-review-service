from app.providers.llm import (
    scan_llm_chunks,
)
from app.providers.mock import (
    scan_mock_chunk,
    sort_and_deduplicate,
)
from app.services.diff_parser import (
    chunk_diff,
)
from app.state import (
    cache_store,
    get_cache_lock,
    job_semaphore,
    jobs,
    publish_event,
    state_lock,
)


async def process_review_job(
    job_id: str,
) -> None:
    async with job_semaphore:
        async with state_lock:
            job = jobs[job_id]
            job["status"] = "running"

        await publish_event(
            job_id,
            "status",
            {
                "status": "running",
            },
        )

        try:
            diff_chunks = chunk_diff(
                job["diff"]
            )

            cache_key = job["cacheKey"]

            cache_lock = await get_cache_lock(
                cache_key
            )

            cache_hit = False

            async with cache_lock:
                if cache_key in cache_store:
                    all_findings = (
                        cache_store[cache_key]
                    )

                    cache_hit = True

                else:
                    if job["provider"] == "mock":
                        combined_findings = []

                        for chunk in diff_chunks:
                            chunk_findings = (
                                scan_mock_chunk(
                                    chunk
                                )
                            )

                            combined_findings.extend(
                                chunk_findings
                            )

                        all_findings = (
                            sort_and_deduplicate(
                                combined_findings
                            )
                        )

                    elif job["provider"] == "llm":
                        all_findings = (
                            await scan_llm_chunks(
                                diff_chunks
                            )
                        )

                    else:
                        raise RuntimeError(
                            "Unknown provider"
                        )

                    cache_store[
                        cache_key
                    ] = all_findings

            visible_findings = all_findings[
                :job["maxFindings"]
            ]

            usage = {
                "inputBytes": len(
                    job["diff"].encode(
                        "utf-8"
                    )
                ),
                "chunks": len(diff_chunks),
                "cacheHit": cache_hit,
            }

            async with state_lock:
                job["findings"] = (
                    visible_findings
                )

                job["usage"] = usage

            for finding in visible_findings:
                await publish_event(
                    job_id,
                    "finding",
                    finding,
                )

            async with state_lock:
                job["status"] = "done"

            await publish_event(
                job_id,
                "status",
                {
                    "status": "done",
                },
            )

            await publish_event(
                job_id,
                "done",
                {
                    "total": len(
                        visible_findings
                    ),
                    "usage": usage,
                },
            )

        except Exception as exception:
            async with state_lock:
                job["status"] = "failed"
                job["error"] = str(exception)

            await publish_event(
                job_id,
                "status",
                {
                    "status": "failed",
                },
            )

            await publish_event(
                job_id,
                "done",
                {
                    "total": 0,
                    "usage": job["usage"],
                    "error": str(exception),
                },
            )