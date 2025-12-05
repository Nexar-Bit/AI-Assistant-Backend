from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, chat, chat_websocket, consultations, reports, tokens, upload, users, vehicles, workshops
from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.logging import LoggingMiddleware


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Vehicle Diagnostics AI Platform",
        version="0.1.0",
    )

    # CORS middleware - must be added before other middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware
    app.add_middleware(LoggingMiddleware)

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

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    return app


app = create_app()


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )

