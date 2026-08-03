# AI Diff Review Service

AI diff review HTTP service developed for the Xsolla
AI-First Engineering Intern technical assessment.

## Features

- Asynchronous review jobs
- Bearer token authentication
- Deterministic mock provider
- Structured findings
- File-boundary chunking
- Idempotency handling
- Result caching
- Server-Sent Events
- Completed-job SSE replay
- Rate limiting
- Four concurrent jobs
- Graceful LLM provider failure

## Local setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload