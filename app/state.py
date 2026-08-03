import asyncio
import time

from collections import defaultdict, deque
from typing import Any, Optional

from app.config import (
    MAX_CONCURRENT_JOBS,
    RATE_LIMIT_PER_MINUTE,
)


jobs: dict[str, dict[str, Any]] = {}

idempotency_store: dict[
    str,
    dict[str, str],
] = {}

cache_store: dict[
    str,
    list[dict[str, Any]],
] = {}

event_store: dict[
    str,
    list[tuple[str, dict[str, Any]]],
] = defaultdict(list)

subscribers: dict[
    str,
    list[asyncio.Queue],
] = defaultdict(list)

rate_buckets: dict[
    str,
    deque,
] = defaultdict(deque)

cache_locks: dict[
    str,
    asyncio.Lock,
] = {}

state_lock = asyncio.Lock()
rate_lock = asyncio.Lock()

job_semaphore = asyncio.Semaphore(
    MAX_CONCURRENT_JOBS
)


async def get_cache_lock(
    cache_key: str,
) -> asyncio.Lock:
    async with state_lock:
        if cache_key not in cache_locks:
            cache_locks[cache_key] = (
                asyncio.Lock()
            )

        return cache_locks[cache_key]


async def publish_event(
    job_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    async with state_lock:
        event_store[job_id].append(
            (event_type, data)
        )

        current_subscribers = list(
            subscribers[job_id]
        )

    for subscriber in current_subscribers:
        await subscriber.put(
            (event_type, data)
        )


async def check_rate_limit(
    client_identifier: str,
) -> Optional[int]:
    current_time = time.time()

    async with rate_lock:
        bucket = rate_buckets[
            client_identifier
        ]

        while (
            bucket
            and current_time - bucket[0] >= 60
        ):
            bucket.popleft()

        if (
            len(bucket)
            >= RATE_LIMIT_PER_MINUTE
        ):
            retry_after = int(
                60 - (
                    current_time
                    - bucket[0]
                )
            )

            return max(retry_after, 1)

        bucket.append(current_time)

    return None