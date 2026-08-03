import time

from fastapi import FastAPI

app = FastAPI(
    title="AI Diff Review Service",
    version="1.0.0",
)

start_time = time.time()


@app.get("/")
async def root():
    return {
        "message": "AI Diff Review Service is running"
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "uptimeSeconds": round(time.time() - start_time, 2),
    }


@app.get("/spec")
async def spec():
    return {
        "specVersion": "1.0",
        "providers": ["mock", "llm"],
        "limits": {
            "maxPayloadBytes": 1048576,
            "chunkBytes": 65536,
            "maxConcurrentJobs": 4,
            "rateLimitPerMinute": 30,
        },
    }