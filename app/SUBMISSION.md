
# 19. `SUBMISSION.md`

```markdown
# Submission

## Architecture

The service is implemented using FastAPI.

Review requests are validated and stored as asynchronous jobs.
Jobs move through queued, running, done, or failed states.

A semaphore limits processing to four concurrent jobs. Further
jobs remain queued instead of failing.

The provider design separates the deterministic mock scanner
from the LLM provider path.

Unified diffs are split at file boundaries into chunks of at
most 64 KiB. A single file larger than 64 KiB becomes its own
chunk.

Findings are deduplicated by ID and ordered by path, line, and
rule ID.

In-memory event storage supports live SSE delivery and identical
replay after a job has finished.

## Provider design

The mock provider implements MOCK-001 through MOCK-008 and
MOCK-INJ. It scans only added lines and excludes the +++ file
header.

The LLM provider follows the same processing path. Because model
credentials are not included in the repository, it fails the job
gracefully with a clear provider-unavailable error.

## Chunking verification

I tested a multi-file diff larger than 64 KiB. Files were grouped
without splitting an individual file across chunks. A single
large file was placed in its own chunk.

I compared chunked and normal findings to confirm that ordering
and deduplication remained consistent.

## Caching verification

I submitted the same diff and options twice. The second job
returned identical findings with cacheHit set to true.

## Idempotency verification

The same Idempotency-Key and byte-identical request body returned
the same job ID.

Reusing the same key with a different request body returned HTTP
409 with the idempotency_conflict error code.

## SSE replay verification

I connected to the stream while a job was running and received
status, finding, and done events.

I connected again after completion and confirmed that the stored
events were replayed in the same order.

## Rate limiting and concurrency

POST review submissions are limited to 30 per minute per client.
GET endpoints are not rate limited.

Four jobs can enter processing concurrently. Additional jobs
remain queued until capacity becomes available.

## AI tools used

I used ChatGPT to review the task contract, structure the FastAPI
project, generate edge cases, and help inspect implementation
decisions.

## AI suggestion rejected

An AI-generated suggestion proposed performing the complete
review inside the POST request.

I rejected it because the contract explicitly requires an
asynchronous lifecycle and an immediate HTTP 202 queued response.

## What I would do next

With more time, I would:

- Replace in-memory storage with PostgreSQL.
- Use Redis and a durable worker queue.
- Add distributed rate limiting.
- Add automated integration and load tests.
- Configure a production LLM provider.
- Add structured logging, tracing, and metrics.