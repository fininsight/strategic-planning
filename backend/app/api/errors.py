from __future__ import annotations

from typing import Union

from fastapi.responses import JSONResponse


def api_error(status: int, code: str, exc: Union[Exception, str]) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": str(exc)})
