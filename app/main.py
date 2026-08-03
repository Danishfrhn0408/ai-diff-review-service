import asyncio
import hashlib
import json
import secrets
import time
import uuid
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    Header,
    Request,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)

from app.auth import verify_token
from app.config import (
    API_TOKEN,
    APP_VERSION,
    CHUNK_BYTES,
    MAX_CONCURRENT_JOBS,
    MAX_PAYLOAD_BYTES,
    RATE_LIMIT_PER_MINUTE,
    SPEC_VERSION,
)
from app.errors import api_error
from app.models import (
    ReviewOptions,
    ReviewRequest,
)
from app.services.diff_parser import (
    chunk_diff,
    is_valid_unified_diff,
)
from app.services.review_service import (
    process_review_job,
)
from app.state import (
    check_rate_limit,
    event_store,
    idempotency_store,
    jobs,
    publish_event,
    state_lock,
    subscribers,
)


app = FastAPI(
    title="AI Diff Review Service",
    version=APP_VERSION,
)

started_at = time.time()


@app.middleware("http")
async def protect_all_v1_routes(
    request: Request,
    call_next,
):
    if request.url.path.startswith("/v1/"):
        authorization = request.headers.get(
            "Authorization",
            "",
        )

        expected_authorization = (
            f"Bearer {API_TOKEN}"
        )

        if not secrets.compare_digest(
            authorization,
            expected_authorization,
        ):
            return api_error(
                401,
                "unauthorized",
                "Invalid or missing bearer token",
            )

    return await call_next(request)


@app.exception_handler(
    RequestValidationError
)
async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
):
    errors = exception.errors()

    invalid_json = any(
        error.get("type") == "json_invalid"
        for error in errors
    )

    if invalid_json:
        return api_error(
            400,
            "invalid_json",
            "Request body must be valid JSON",
        )

    return api_error(
        422,
        "invalid_diff",
        "Missing or invalid diff",
    )


@app.exception_handler(
    StarletteHTTPException
)
async def http_exception_handler(
    request: Request,
    exception: StarletteHTTPException,
):
    detail = exception.detail

    if (
        isinstance(detail, dict)
        and "code" in detail
        and "message" in detail
    ):
        return api_error(
            exception.status_code,
            detail["code"],
            detail["message"],
            exception.headers,
        )

    if exception.status_code == 404:
        return api_error(
            404,
            "not_found",
            "Resource not found",
        )

    if exception.status_code == 401:
        return api_error(
            401,
            "unauthorized",
            "Invalid or missing bearer token",
        )

    return api_error(
        exception.status_code,
        "internal",
        str(detail),
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exception: Exception,
):
    print(
        "Unhandled server error:",
        repr(exception),
    )

    return api_error(
        500,
        "internal",
        "Internal server error",
    )


def create_body_hash(
    raw_body: bytes,
) -> str:
    return hashlib.sha256(
        raw_body
    ).hexdigest()


def create_cache_key(
    diff: str,
    options: ReviewOptions,
) -> str:
    canonical_content = json.dumps(
        {
            "diff": diff,
            "options": options.model_dump(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_content.encode("utf-8")
    ).hexdigest()


def format_sse_event(
    event_type: str,
    data: dict,
) -> str:
    encoded_data = json.dumps(
        data,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return (
        f"event: {event_type}\n"
        f"data: {encoded_data}\n\n"
    )


@app.get("/")
async def root():
    return {
        "service": "AI Diff Review Service",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "uptimeSeconds": round(
            time.time() - started_at,
            3,
        ),
    }


@app.get("/spec")
async def spec():
    return {
        "specVersion": SPEC_VERSION,
        "providers": [
            "mock",
            "llm",
        ],
        "limits": {
            "maxPayloadBytes": (
                MAX_PAYLOAD_BYTES
            ),
            "chunkBytes": CHUNK_BYTES,
            "maxConcurrentJobs": (
                MAX_CONCURRENT_JOBS
            ),
            "rateLimitPerMinute": (
                RATE_LIMIT_PER_MINUTE
            ),
        },
    }


@app.post(
    "/v1/reviews",
    status_code=202,
    dependencies=[
        Depends(verify_token)
    ],
)
async def create_review(
    request: Request,
    review_request: ReviewRequest,
    idempotency_key: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    raw_body = await request.body()

    if len(raw_body) > MAX_PAYLOAD_BYTES:
        return api_error(
            413,
            "payload_too_large",
            "Payload exceeds 1 MiB",
        )

    client_identifier = (
        request.client.host
        if request.client
        else "unknown"
    )

    retry_after = await check_rate_limit(
        client_identifier
    )

    if retry_after is not None:
        return api_error(
            429,
            "rate_limited",
            "Rate limit exceeded",
            headers={
                "Retry-After": str(
                    retry_after
                )
            },
        )

    if not is_valid_unified_diff(
        review_request.diff
    ):
        return api_error(
            422,
            "invalid_diff",
            (
                "diff must be a parseable "
                "unified diff"
            ),
        )

    if (
        review_request.options.provider
        not in {
            "mock",
            "llm",
        }
    ):
        return api_error(
            422,
            "invalid_diff",
            "Provider must be mock or llm",
        )

    request_body_hash = create_body_hash(
        raw_body
    )

    cache_key = create_cache_key(
        review_request.diff,
        review_request.options,
    )

    async with state_lock:
        if idempotency_key:
            existing_record = (
                idempotency_store.get(
                    idempotency_key
                )
            )

            if existing_record:
                existing_body_hash = (
                    existing_record[
                        "bodyHash"
                    ]
                )

                if (
                    existing_body_hash
                    != request_body_hash
                ):
                    return api_error(
                        409,
                        "idempotency_conflict",
                        (
                            "Idempotency key was "
                            "already used with a "
                            "different request body"
                        ),
                    )

                existing_job_id = (
                    existing_record[
                        "jobId"
                    ]
                )

                return {
                    "jobId": existing_job_id,
                    "status": jobs[
                        existing_job_id
                    ]["status"],
                }

        job_id = uuid.uuid4().hex

        diff_chunks = chunk_diff(
            review_request.diff
        )

        jobs[job_id] = {
            "jobId": job_id,
            "status": "queued",
            "diff": review_request.diff,
            "provider": (
                review_request
                .options
                .provider
            ),
            "maxFindings": (
                review_request
                .options
                .maxFindings
            ),
            "cacheKey": cache_key,
            "findings": [],
            "usage": {
                "inputBytes": len(
                    review_request.diff.encode(
                        "utf-8"
                    )
                ),
                "chunks": len(
                    diff_chunks
                ),
                "cacheHit": False,
            },
            "error": None,
        }

        if idempotency_key:
            idempotency_store[
                idempotency_key
            ] = {
                "bodyHash": (
                    request_body_hash
                ),
                "jobId": job_id,
            }

    await publish_event(
        job_id,
        "status",
        {
            "status": "queued",
        },
    )

    asyncio.create_task(
        process_review_job(
            job_id
        )
    )

    return {
        "jobId": job_id,
        "status": "queued",
    }


@app.get(
    "/v1/reviews/{job_id}",
    dependencies=[
        Depends(verify_token)
    ],
)
async def get_review(
    job_id: str,
):
    job = jobs.get(job_id)

    if job is None:
        return api_error(
            404,
            "not_found",
            "Unknown jobId",
        )

    response = {
        "jobId": job_id,
        "status": job["status"],
        "usage": job["usage"],
    }

    if job["status"] == "done":
        response["findings"] = (
            job["findings"]
        )

    if job["status"] == "failed":
        response["error"] = (
            job["error"]
        )

    return response


@app.get(
    "/v1/reviews/{job_id}/stream",
    dependencies=[
        Depends(verify_token)
    ],
)
async def stream_review(
    job_id: str,
):
    if job_id not in jobs:
        return api_error(
            404,
            "not_found",
            "Unknown jobId",
        )

    async def event_generator():
        subscriber_queue = asyncio.Queue()

        async with state_lock:
            saved_events = list(
                event_store[job_id]
            )

            job_finished = (
                jobs[job_id]["status"]
                in {
                    "done",
                    "failed",
                }
            )

            if not job_finished:
                subscribers[job_id].append(
                    subscriber_queue
                )

        for (
            event_type,
            event_data,
        ) in saved_events:
            yield format_sse_event(
                event_type,
                event_data,
            )

        if job_finished:
            return

        try:
            while True:
                (
                    event_type,
                    event_data,
                ) = await subscriber_queue.get()

                yield format_sse_event(
                    event_type,
                    event_data,
                )

                if event_type == "done":
                    break

        finally:
            async with state_lock:
                if (
                    subscriber_queue
                    in subscribers[job_id]
                ):
                    subscribers[
                        job_id
                    ].remove(
                        subscriber_queue
                    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )