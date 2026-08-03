from typing import Optional

from fastapi.responses import JSONResponse


def api_error(
    status_code: int,
    code: str,
    message: str,
    headers: Optional[dict] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
        headers=headers or {},
    )