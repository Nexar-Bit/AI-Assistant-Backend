#!/bin/bash
# Start script for Render deployment
set -e

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Check migration status
echo "Current migration status:"
alembic current

# Get port from environment (Render provides this)
PORT=${PORT:-8000}

# Use gunicorn in production, uvicorn in development
if [ "$ENVIRONMENT" = "production" ] || [ "$ENVIRONMENT" = "staging" ]; then
    echo "Starting with Gunicorn (Production mode)..."
    exec gunicorn main:app \
        -w 4 \
        -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:$PORT \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --log-level info
else
    echo "Starting with Uvicorn (Development mode)..."
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port $PORT \
        --reload \
        --log-level info
fi

