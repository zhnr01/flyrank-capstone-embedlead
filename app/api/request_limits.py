from fastapi import HTTPException, Request, status

from app.core.config import settings


async def enforce_submission_size_limit(request: Request) -> None:
    declared_length = request.headers.get("content-length")
    if declared_length is None:
        return
    try:
        length = int(declared_length)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Content-Length header",
        ) from None
    if length > settings.max_submission_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Submission payload too large",
        )
