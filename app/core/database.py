from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings


def get_database_url() -> str:
    """Get database URL with SSL support for production databases."""
    base_url = (
        f"postgresql+psycopg2://{settings.POSTGRES_USER}:"
        f"{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:"
        f"{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    
    # Render PostgreSQL requires SSL connections
    # Add SSL mode if connecting to a Render database (detected by .render.com in hostname)
    if ".render.com" in settings.POSTGRES_HOST or settings.ENVIRONMENT.lower() in ("production", "staging"):
        # Use sslmode=require for Render PostgreSQL
        # This ensures SSL is used but doesn't verify the certificate (suitable for Render)
        if "?" not in base_url:
            base_url += "?sslmode=require"
        else:
            base_url += "&sslmode=require"
    
    return base_url


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


