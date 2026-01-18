from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
import logging
import os

from config import settings
from database import init_db
from api.endpoints import auth
from api.v1 import endpoints as v1_endpoints
from api.v1 import kb_document_endpoints as v1_kb_doc_endpoints
from services.scheduler import (
    agent_purge_scheduler,
    url_fetch_scheduler,
    history_cleanup_scheduler,
    session_auto_close_scheduler,
)
from services.redis_service import get_redis, close_redis
from middleware import RateLimitMiddleware, apply_cors_headers, get_request_client_ip
from middleware.rate_limit import apply_cors_headers as apply_early_cors_headers
from i18n.core import I18nMiddleware

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    test_mode = os.getenv("BASJOO_TEST_MODE") == "1"

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization complete")

    if not test_mode:
        logger.info("Initializing Redis connection...")
        try:
            redis = await get_redis()
            if await redis.health_check():
                logger.info("Redis connection successful")
            else:
                logger.warning("Redis connection failed, using in-memory rate limiting")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}, using in-memory rate limiting")

        logger.info("Starting URL fetch scheduler...")
        url_fetch_scheduler.start()
        logger.info("URL fetch scheduler started")

        logger.info("Starting history cleanup scheduler...")
        history_cleanup_scheduler.start()
        logger.info("History cleanup scheduler started")

        logger.info("Starting session auto-close scheduler...")
        session_auto_close_scheduler.start()
        logger.info("Session auto-close scheduler started")

        logger.info("Starting agent cleanup scheduler...")
        await agent_purge_scheduler.purge_expired_agents()
        agent_purge_scheduler.start()
        logger.info("Agent cleanup scheduler started")
    else:
        logger.info("Test mode enabled, skipping Redis and scheduler startup")

    yield

    if not test_mode:
        logger.info("Stopping URL fetch scheduler...")
        url_fetch_scheduler.stop()
        logger.info("URL fetch scheduler stopped")

        logger.info("Stopping history cleanup scheduler...")
        history_cleanup_scheduler.stop()
        logger.info("History cleanup scheduler stopped")

        logger.info("Stopping session auto-close scheduler...")
        session_auto_close_scheduler.stop()
        logger.info("Session auto-close scheduler stopped")

        logger.info("Stopping agent cleanup scheduler...")
        agent_purge_scheduler.stop()
        logger.info("Agent cleanup scheduler stopped")

        logger.info("Closing Redis connection...")
        await close_redis()

    logger.info("Application shutdown")


app = FastAPI(
    title=settings.app_name,
    description="AI Agent system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
)


@app.middleware("http")
async def cors_for_file_protocol(request, call_next):
    """Apply the shared early-response CORS policy to normal responses too."""
    response = await call_next(request)
    return apply_early_cors_headers(request, response)


app.add_middleware(I18nMiddleware)

app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=settings.rate_limit_per_minute,
    burst_size=settings.rate_limit_burst_size,
)


@app.middleware("http")
async def log_requests(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        content_length = int(content_length)
        max_size = 10 * 1024 * 1024
        if content_length > max_size:
            logger.warning(
                f"Request too large: {content_length} bytes from "
                f"{get_request_client_ip(request)}"
            )
            from fastapi.responses import JSONResponse

            response = JSONResponse(
                status_code=413,
                content={
                    "detail": f"Request body too large, maximum allowed: {max_size // (1024 * 1024)}MB"
                },
            )
            return apply_cors_headers(request, response)

    logger.info(f"REQUEST: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(
            f"RESPONSE: {response.status_code} {request.method} {request.url.path}"
        )
        return response
    except Exception as e:
        logger.exception(f"ERROR processing {request.method} {request.url.path}: {e}")
        raise


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    """Return JSON for unhandled exceptions instead of plain-text 500."""
    logger = logging.getLogger("uvicorn")
    logger.exception(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Auth API (kept for frontend login/register)
app.include_router(auth.router, prefix="/api/admin", tags=["auth"])

# v1 API
app.include_router(v1_endpoints.router, tags=["v1"])
app.include_router(v1_kb_doc_endpoints.router, tags=["kb-documents"])


@app.get("/sdk.js")
async def get_sdk_js():
    """Return widget SDK file"""
    sdk_path = os.path.join(os.path.dirname(__file__), "static", "sdk.js")
    if os.path.exists(sdk_path):
        return FileResponse(sdk_path, media_type="application/javascript")
    return {"error": "SDK not found"}


@app.get("/basjoo-logo.png")
async def get_logo():
    """Return widget logo file"""
    logo_path = os.path.join(os.path.dirname(__file__), "static", "basjoo-logo.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    return {"error": "Logo not found"}


@app.get("/widget-demo", response_class=HTMLResponse)
async def get_widget_demo():
    """Return widget embed demo page"""
    demo_path = os.path.join(os.path.dirname(__file__), "static", "widget-demo.html")
    if os.path.exists(demo_path):
        with open(demo_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Error: Demo page not found</h1>"


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.app_name} API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level,
    )
