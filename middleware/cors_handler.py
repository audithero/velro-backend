"""
CORS middleware handler.
Must be the outermost middleware to ensure headers on all responses.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

logger = logging.getLogger(__name__)


def add_cors_middleware(app: FastAPI):
    """
    Add CORS middleware to the app.
    This MUST be called LAST so it becomes the outermost middleware.
    """
    origins = settings.CORS_ORIGINS
    
    logger.info(f"🌐 [CORS] Configuring with {len(origins)} origins")
    logger.info(f"🌐 [CORS] Origins: {', '.join(origins[:3])}...")  # Log first 3
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "Server-Timing",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        max_age=settings.CORS_MAX_AGE,
    )
    
    logger.info("✅ [CORS] Middleware added as OUTERMOST layer")
    logger.info(f"✅ [CORS] Credentials: {settings.ALLOW_CREDENTIALS}")
    logger.info(f"✅ [CORS] Max age: {settings.CORS_MAX_AGE}s")