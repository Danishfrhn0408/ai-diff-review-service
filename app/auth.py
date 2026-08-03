import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from app.config import API_TOKEN


bearer_scheme = HTTPBearer(auto_error=False)


async def verify_token(
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": (
                    "Invalid or missing bearer token"
                ),
            },
        )

    valid_scheme = (
        credentials.scheme.lower() == "bearer"
    )

    valid_token = secrets.compare_digest(
        credentials.credentials,
        API_TOKEN,
    )

    if not valid_scheme or not valid_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": (
                    "Invalid or missing bearer token"
                ),
            },
        )

    return credentials.credentials