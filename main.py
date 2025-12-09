import os
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import admin, auth, chat, chat_websocket, consultations, reports, tokens, upload, users, vehicles, workshops, ai_providers, registration_admin
from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.logging import LoggingMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Vehicle Diagnostics AI Platform",
        version="0.1.0",
    )

    # CORS middleware - must be added before other middleware
    # Get allowed origins from environment or use defaults
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    # Always add the Vercel production URL
    allowed_origins.append("https://ai-assistant-ivory-sigma.vercel.app")
    
    # Add production frontend URL if provided
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        allowed_origins.append(frontend_url)
    
    # Add Vercel frontend URL (for preview deployments)
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        # Vercel provides URL without protocol, add https
        if not vercel_url.startswith("http"):
            allowed_origins.append(f"https://{vercel_url}")
        else:
            allowed_origins.append(vercel_url)
    
    # In production, allow all origins if CORS_ORIGINS is set to "*"
    cors_origins = os.getenv("CORS_ORIGINS", "")
    if cors_origins == "*":
        allowed_origins = ["*"]
    elif cors_origins:
        # Allow multiple origins separated by comma
        allowed_origins.extend([origin.strip() for origin in cors_origins.split(",")])
    
    # Log allowed origins for debugging
    logger.info(f"CORS allowed origins: {allowed_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Middleware
    app.add_middleware(LoggingMiddleware)
    
    # Helper function to get CORS origin header
    def get_cors_origin(request: Request) -> str:
        """Get the appropriate CORS origin header value."""
        origin = request.headers.get("origin")
        if origin and (origin in allowed_origins or "*" in allowed_origins):
            return origin
        # Default to first allowed origin or "*" if all origins allowed
        if "*" in allowed_origins:
            return "*"
        return allowed_origins[0] if allowed_origins else "*"
    
    # Global exception handlers to ensure CORS headers are always sent
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions with CORS headers."""
        cors_origin = get_cors_origin(request)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation errors with CORS headers."""
        cors_origin = get_cors_origin(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
            headers={
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions with CORS headers and logging."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        cors_origin = get_cors_origin(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
            headers={
                "Access-Control-Allow-Origin": cors_origin,
                "Access-Control-Allow-Credentials": "true",
            }
        )

    # API routes
    prefix = settings.API_V1_PREFIX
    app.include_router(auth.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(workshops.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(chat_websocket.router, prefix=prefix)
    app.include_router(tokens.router, prefix=prefix)
    app.include_router(consultations.router, prefix=prefix)  # Legacy, keep for backward compatibility
    app.include_router(vehicles.router, prefix=prefix)
    app.include_router(upload.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(ai_providers.router, prefix=prefix)
    app.include_router(registration_admin.router, prefix=prefix)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()


if __name__ == "__main__":
    import os
    import uvicorn

    # Get port from environment (Render provides this)
    port = int(os.getenv("PORT", "8000"))
    # Only enable reload in development
    reload = os.getenv("ENVIRONMENT", "development").lower() == "development"
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info",
    )

