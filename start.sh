#!/bin/bash
# Railway startup script for Velro backend

# Get PORT from environment, default to 8000 if not set  
export ACTUAL_PORT=${PORT:-8000}

echo "🚀 Starting Velro API backend..."
echo "📍 Port: $ACTUAL_PORT"
echo "🌐 Domain: $RAILWAY_PUBLIC_DOMAIN"
echo "🐍 Python: $(python --version)"

# Change to app directory
cd /app 2>/dev/null || cd .

# Start FastAPI with uvicorn
echo "🔥 Starting uvicorn server on port $ACTUAL_PORT..."
exec uvicorn main:app --host 0.0.0.0 --port $ACTUAL_PORT --log-level info