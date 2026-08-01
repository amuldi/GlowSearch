import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.api.search_routes import router as search_router
from app.core.config import get_settings
from app.indexing import turso_backup
from app.service.factory import get_search_provider, get_search_service


class _RateLimitMiddleware(BaseHTTPMiddleware):
    """Generous per-IP request cap so abusive traffic can't amplify into the
    upstream sources we proxy (Olive Young public API, Shopify brand feeds).
    Limits are high enough that no normal user should ever notice them.
    """

    def __init__(self, app, *, max_requests: int = 120, window_seconds: float = 60.0):
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[client_host]
        while hits and now - hits[0] > self._window_seconds:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
            )
        hits.append(now)
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        turso_task: asyncio.Task | None = None
        if settings.product_index_enabled:
            service = get_search_service()
            if settings.product_index_verified_catalog_backfill_on_startup:
                app.state.product_index_verified_catalog_backfill_count = (
                    await service.backfill_verified_catalog()
                )
            if settings.product_index_warmup_on_startup:
                app.state.product_index_warmup_scheduled_queries = service.schedule_warm_index()
            if settings.turso_database_url:
                # Fire-and-forget: never awaited here, so however long Turso
                # takes to respond can never delay startup or a request.
                turso_task = asyncio.create_task(
                    turso_backup.run_periodic(settings.product_index_path, settings)
                )
        yield
        if turso_task is not None:
            turso_task.cancel()
        await get_search_service().close()
        if get_search_provider.cache_info().currsize:
            await get_search_provider().close()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(_RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix=settings.api_prefix)
    app.include_router(search_router, prefix=settings.api_prefix)

    return app


app = create_app()
