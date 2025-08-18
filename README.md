# Velro Backend API

FastAPI-based backend service for the Velro AI-powered creative platform.

## 🚀 Quick Start

### Railway Deployment (Production)
This service is automatically deployed to Railway when pushed to the main branch.

**Production URL**: `https://velro-backend-production.up.railway.app`

### Health Checks
- **Health**: `GET /health`
- **Version**: `GET /__version`
- **API Documentation**: `GET /docs`

### Recent Updates (Dec 17, 2024)
- ✅ Fixed authentication middleware public paths configuration
- ✅ Added comprehensive list of public endpoints
- ✅ Resolved 401 errors on public API endpoints
- 🧹 Cleaned up duplicate files and legacy code

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.template .env
# Edit .env with your configuration

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## 🏗️ Architecture

### Core Technologies
- **FastAPI** 0.104.1 - Modern Python web framework
- **Supabase** - Database and authentication
- **Redis** - Caching and session management
- **FAL AI** - Image generation services

### Key Features
- 🔐 JWT-based authentication with Supabase
- 🚀 Redis caching for <50ms auth performance
- 🎨 AI image generation integration
- 📊 Comprehensive monitoring and logging
- 🔒 Production-ready security hardening

### API Endpoints
- `/api/v1/auth/*` - Authentication and user management
- `/api/v1/projects/*` - Project management
- `/api/v1/generations/*` - AI image generation
- `/api/v1/credits/*` - Credit system
- `/api/v1/models/*` - AI model information
- `/api/v1/storage/*` - File storage and media URLs

## 🔐 Environment Variables

### Required
```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=eyJ...  # anon key
SUPABASE_SECRET_KEY=eyJ...       # service_role key

# JWT Configuration
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_SECONDS=3600

# Redis (Railway provided)
REDIS_URL=redis://default:password@host:port

# AI Services
FAL_KEY=your-fal-api-key
```

### Optional
```env
# Performance
DATABASE_POOL_ENABLED=true
PORT=8080

# Security
ALLOWED_HOSTS=your-domain.com,localhost

# Kong Gateway (if used)
KONG_PROXY_ENABLED=true
KONG_URL=https://your-kong-gateway.com
```

## 🧪 Testing

### Run Tests
```bash
# Unit tests
pytest tests/ -v

# Integration tests
pytest tests/test_integration.py -v

# End-to-end tests
python scripts/test_e2e.py
```

### Performance Testing
```bash
# Authentication performance
./scripts/test-auth-performance.sh

# Load testing
python scripts/load_test.py
```

## 📊 Monitoring

### Health Endpoints
- `GET /health` - Basic service health
- `GET /__version` - Service version and deployment info
- `GET /api/v1/auth-health/status` - Authentication system health

### Public Endpoints (No Authentication Required)
The following endpoints are configured as public and don't require authentication:
- `/api/v1/auth/login` - User login
- `/api/v1/auth/register` - User registration
- `/api/v1/auth/refresh` - Token refresh
- `/api/v1/generations/models/supported` - List supported AI models
- `/api/v1/models` - Models information
- All health and diagnostic endpoints
- API documentation (`/docs`, `/redoc`, `/openapi.json`)

### Performance Targets
- Authentication: <50ms response time
- Database queries: <100ms average
- Redis cache hit rate: >90%
- Service startup: <30 seconds

### Logging
- Structured JSON logging with correlation IDs
- Performance monitoring for all endpoints
- Security event tracking
- Error tracking and alerting

## 🚢 Deployment

### Railway Deployment
1. Connect this repository to Railway service
2. Environment variables are automatically loaded
3. Service deploys on git push to main branch
4. Health checks verify successful deployment

### Configuration Files
- `nixpacks.toml` - Railway build configuration
- `requirements.txt` - Python dependencies
- `main.py` - Application entry point

### Database Initialization
The application requires proper async database initialization during startup. The `main.py` lifespan function calls `initialize_database_async()` which:
- Initializes the singleton SupabaseClient
- Warms up anonymous and service client connections
- Pre-loads connection pools for optimal performance
- Targets <500ms initialization time

**Note**: If the generation service returns 503 errors, verify that `initialize_database_async()` is being called in the startup sequence.

### Rollback Strategy
```bash
# Emergency rollback (if needed)
./scripts/rollback-backend-link.sh
```

## 🔧 Development

### Code Structure
```
├── main.py                 # FastAPI app and configuration
├── database.py            # Database connection and models
├── config.py              # Settings and configuration
├── routers/               # API route handlers
├── services/              # Business logic services
├── models/                # Pydantic models and schemas
├── middleware/            # Custom middleware
├── utils/                 # Utility functions
├── caching/               # Redis caching system
├── security/              # Security utilities
└── monitoring/            # Logging and metrics
```

### Adding New Endpoints
1. Create router in `routers/`
2. Add business logic in `services/`
3. Define models in `models/`
4. Include router in `main.py`
5. Add tests in `tests/`

### Performance Guidelines
- Use async/await for all I/O operations
- Implement proper caching strategies
- Add comprehensive error handling
- Include monitoring and logging
- Follow security best practices

## 📝 License

Proprietary - All rights reserved

## 🤝 Contributing

1. Create feature branch from `main`
2. Implement changes with tests
3. Ensure performance targets are met
4. Submit pull request with clear description

## 📞 Support

For deployment issues or technical support, please contact the development team.

---

**Last Updated**: August 2025
**Service Version**: 1.1.5-recovery
**Railway Deployment**: ✅ Active

## 🐛 Known Issues & Fixes

### Generation Service 503 Errors
**Issue**: Generation endpoints return "Database not initialized" errors.
**Cause**: Missing `initialize_database_async()` call in startup sequence.
**Fix**: Ensure main.py lifespan function includes database async initialization.

### Authentication Performance
**Target**: <50ms response time
**Achieved**: ✅ Using Supabase JWT validation with caching