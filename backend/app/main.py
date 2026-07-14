from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import routers


def create_app() -> FastAPI:
    app = FastAPI(
        title="FI Strategic Planning Analysis API",
        description="나라장터 공고, 첨부파일, 제안 분석, 전략 수립 데이터를 제공하는 API입니다.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "PUT", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    for router in routers:
        app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("ANALYSIS_HOST", "127.0.0.1")
    port = int(os.getenv("ANALYSIS_PORT", "8787"))
    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
