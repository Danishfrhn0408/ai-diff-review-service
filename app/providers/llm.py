from typing import Any


async def scan_llm_chunks(
    chunks: list[str],
) -> list[dict[str, Any]]:
    raise RuntimeError(
        "LLM provider unavailable: "
        "configure model access and credentials "
        "on the server"
    )