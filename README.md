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
**Service Version**: 1.1.3
**Railway Deployment**: ✅ Active