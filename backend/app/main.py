"""FastAPI application entry point for faux_code."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat as chat_api
from .api import models as models_api
from .api import settings as settings_api
from .db import init_db
from .settings import get_settings


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    init_db()
    settings_api.load_keys_into_env()
    # Refresh after loading DB keys so providers pick them up.
    from .settings import get_settings as gs

    gs.__globals__["_settings"] = None  # type: ignore[attr-defined]
    from .providers.registry import reload_providers

    reload_providers()
    log = structlog.get_logger()
    log.info("faux_code.start", host=settings.host, port=settings.port)
    yield
    log.info("faux_code.stop")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="faux_code", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_api.router)
    app.include_router(models_api.router)
    app.include_router(settings_api.router)
    # Agent + RAG + tools routers attached in later phases.
    try:
        from .api import agents as agents_api  # noqa: F401

        app.include_router(agents_api.router)
    except Exception:
        pass
    try:
        from .api import rag as rag_api  # noqa: F401

        app.include_router(rag_api.router)
    except Exception:
        pass
    try:
        from .api import workspace as workspace_api  # noqa: F401

        app.include_router(workspace_api.router)
    except Exception:
        pass

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "service": "faux_code", "version": "0.1.0"}

    return app


app = create_app()


def run() -> None:
    """Entry-point exposed as a `faux-code-server` console script."""
    s = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=s.host,
        port=s.port,
        reload=False,
        log_level=s.log_level.lower(),
    )


if __name__ == "__main__":
    run()
