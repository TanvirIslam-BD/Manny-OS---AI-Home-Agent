"""Manny OS FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from manny import __version__
from manny.api.routes import router
from manny.config import Settings, get_settings
from manny.lifecycle import build_services
from manny.observability.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        services = build_services(resolved)
        application.state.services = services
        await services.start()
        try:
            yield
        finally:
            await services.stop()

    application = FastAPI(
        title="Manny OS",
        version=__version__,
        docs_url="/docs" if resolved.environment == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            # The device has no external browser, so OAuth sign-in renders in an
            # embedded webview. Framing is limited to HTTPS provider pages.
            "frame-src https:"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    application.include_router(router, prefix="/api")
    ui_dist = Path(__file__).resolve().parents[2] / "ui" / "dist"
    if ui_dist.exists():
        application.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")
    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    runtime_settings = get_settings()
    uvicorn.run(
        "manny.main:app",
        host=runtime_settings.api_host,
        port=runtime_settings.api_port,
        app_dir="apps/core",
        reload=runtime_settings.environment == "development",
        access_log=False,
    )
