from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.search_routes import router as search_router
from app.core.config import get_settings
from app.service.factory import get_search_provider, get_search_service


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
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

    @app.on_event("startup")
    async def warm_product_index() -> None:
        if not settings.product_index_enabled or not settings.product_index_warmup_on_startup:
            return
        scheduled_queries = get_search_service().schedule_warm_index()
        app.state.product_index_warmup_scheduled_queries = scheduled_queries

    @app.on_event("shutdown")
    async def shutdown_search_service() -> None:
        await get_search_service().close()
        if get_search_provider.cache_info().currsize:
            await get_search_provider().close()

    return app


app = create_app()
