# Render Quick Setup Guide

## ✅ Current Status

Based on your logs, the service is **LIVE** at:
- **URL**: https://ai-assist-backend-ex3q.onrender.com
- **Status**: Running on port 10000
- **Health Check**: Available at `/health`

## ⚠️ Issues to Fix

### 1. Port Detection Warning
Render shows "No open ports detected" but the service is running. This is because:
- The server is using `python main.py` (development mode)
- Should use Gunicorn for production

### 2. Redis Warning (Optional)
```
Redis not available: Error -2 connecting to redis:6379
```
This is **optional** - the app will work without Redis, but some features will be disabled:
- Rate limiting
- Refresh token rotation

## 🔧 Recommended Fixes

### Fix 1: Update Start Command in Render

1. Go to your Render dashboard
2. Select your service: `ai-assist-backend`
3. Go to **Settings** → **Build & Deploy**
4. Find **Start Command**
5. Replace with:
   ```bash
   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 120
   ```
6. Click **Save Changes**
7. Render will automatically redeploy

### Fix 2: Set Required Environment Variables

Go to **Environment** tab and add:

#### Critical (Required)
- `SECRET_KEY` - Generate using: `python scripts/generate_secret_key.py`
- `ENVIRONMENT` - Set to `production`
- `DEBUG` - Set to `false`

#### Database (If using Render PostgreSQL)
- `POSTGRES_HOST` - From your PostgreSQL service
- `POSTGRES_USER` - From your PostgreSQL service
- `POSTGRES_PASSWORD` - From your PostgreSQL service
- `POSTGRES_DB` - From your PostgreSQL service
- `POSTGRES_PORT` - Usually `5432`

#### Optional
- `REDIS_URL` - **Leave unset** if you don't have Redis (app works without it). Only set if you have a Redis service (format: `redis://host:port/0`)
- `OPENAI_API_KEY` - If using AI features

## 🧪 Testing Your Deployment

### 1. Health Check
```bash
curl https://ai-assist-backend-ex3q.onrender.com/health
```

Expected response:
```json
{"status":"ok","environment":"production"}
```

### 2. API Endpoint
```bash
curl https://ai-assist-backend-ex3q.onrender.com/api/v1/
```

## 📝 Current Configuration

Based on logs:
- ✅ Python 3.13.4
- ✅ All dependencies installed
- ✅ Server running on port 10000
- ✅ Service is accessible
- ⚠️ Using development mode (should use Gunicorn)
- ⚠️ Redis not configured (optional)

## 🚀 Next Steps

1. **Update Start Command** to use Gunicorn (see Fix 1 above)
2. **Set Environment Variables** (see Fix 2 above)
3. **Run Database Migrations** (if using PostgreSQL):
   ```bash
   alembic upgrade head
   ```
   You can add this as a build command or run manually after first deploy.

4. **Test the API** using the health check endpoint

## 📚 Additional Resources

- Full deployment guide: `RENDER_DEPLOY.md`
- Environment variables: See `RENDER_DEPLOY.md` for complete list
- Troubleshooting: Check Render logs in dashboard

