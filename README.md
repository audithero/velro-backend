# Velro Backend API

Production-ready FastAPI backend service for the Velro AI generation platform.

## 🚀 Production URLs

- **API Base**: `https://velro-backend-production.up.railway.app`
- **API Documentation**: `https://velro-backend-production.up.railway.app/docs`
- **Health Check**: `https://velro-backend-production.up.railway.app/health`

## 🏗️ Architecture

### Core Technologies
- **FastAPI** 0.104.1 - Modern async Python web framework
- **Supabase** - PostgreSQL database and authentication
- **Redis** - Caching and queue management
- **FAL.ai** - AI model provider (image/video generation)
- **Docker** - Containerized deployment

### Key Features
- 🔐 JWT-based authentication with Supabase
- 🚀 Async non-blocking architecture (100+ concurrent users)
- 🎨 Multiple AI models (FLUX Pro, Imagen 4, Veo 3, etc.)
- 💳 Credit-based usage system
- 📊 Real-time generation status tracking
- 🔒 Production-ready security with parameter validation
- ⚡ Redis caching for optimal performance

## 📁 Project Structure

```
velro-backend/
├── main.py                    # FastAPI application entry point
├── config.py                  # Settings and environment configuration
├── Dockerfile                 # Container configuration
├── requirements.txt           # Python dependencies
├── models/
│   ├── fal_config.py         # ← AI MODEL REGISTRY (Add new models here!)
│   ├── user.py               # User models
│   └── generation.py         # Generation models
├── routers/
│   ├── auth_supabase.py     # Authentication endpoints
│   ├── generations_async.py  # Async generation endpoints
│   ├── credits.py            # Credit management
│   └── projects.py           # Project management
├── services/
│   ├── fal_service_async.py # FAL.ai integration (async)
│   ├── supabase_auth.py     # Supabase authentication
│   └── user_service.py      # User management
├── middleware/
│   ├── auth.py              # JWT authentication middleware
│   └── redis_config.py      # Redis connection management
└── repositories/
    └── user_repository.py    # Database operations
```

## 🎨 AI Models Configuration

Models are defined in `/models/fal_config.py`. No database changes needed!

### Currently Available Models

**Image Generation:**
- `fal-ai/flux-pro/v1.1-ultra` (50 credits)
- `fal-ai/flux-pro/kontext/max` (60 credits)
- `fal-ai/imagen4/preview/ultra` (45 credits)

**Video Generation:**
- `fal-ai/veo3` (500 credits)
- `fal-ai/minimax/hailuo-02/pro/text-to-video` (400 credits)
- `fal-ai/wan-pro/text-to-video` (300 credits)

### Adding New Models

Edit `/models/fal_config.py`:

```python
"fal-ai/your-new-model": FALModelConfig(
    endpoint="fal-ai/your-new-model",
    ai_model_type=FALModelType.IMAGE,  # or VIDEO
    credits=30,  # Credit cost
    max_resolution="2048x2048",
    supported_formats=["jpg", "png"],
    description="Model description",
    parameters={
        "prompt": {"type": "string", "required": True},
        "image_size": {"type": "string", "default": "square"},
        # Add model-specific parameters
    },
    example_params={
        "prompt": "Example prompt",
        "image_size": "square"
    }
)
```

## 🔧 Environment Variables

### Required
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# FAL.ai
FAL_KEY=your-fal-api-key

# Redis (Railway provides this)
REDIS_URL=redis://default:password@velro-redis.railway.internal:6379

# Security
JWT_SECRET=your-secret-key-min-32-chars

# Environment
ENVIRONMENT=production
DEFAULT_USER_CREDITS=1000
```

## 📡 API Endpoints

### Authentication
```
POST   /api/v1/auth/register         # Register new user
POST   /api/v1/auth/login            # Login
GET    /api/v1/auth/me               # Get current user
POST   /api/v1/auth/refresh          # Refresh token
```

### Generation (Async)
```
POST   /api/v1/generations/async/submit         # Submit generation
GET    /api/v1/generations/async/{id}/status    # Check status
GET    /api/v1/generations/async/{id}/stream    # SSE stream
DELETE /api/v1/generations/async/{id}/cancel    # Cancel generation
GET    /api/v1/generations/async/user/history   # User history
GET    /api/v1/generations/models/supported     # List all models
```

### Credits
```
GET    /api/v1/credits/balance              # Get balance
GET    /api/v1/credits/transactions         # Transaction history
POST   /api/v1/credits/purchase            # Purchase credits
```

### Projects
```
GET    /api/v1/projects                    # List projects
POST   /api/v1/projects                    # Create project
GET    /api/v1/projects/{id}              # Get project
PUT    /api/v1/projects/{id}              # Update project
DELETE /api/v1/projects/{id}              # Delete project
```

## 🚀 Local Development

### Setup
```bash
# Clone repository
git clone https://github.com/your-org/velro-003.git
cd velro-003/velro-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your credentials

# Run development server
uvicorn main:app --reload --port 8000
```

### Testing
```bash
# Run tests
pytest tests/ -v

# Test specific endpoint
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test123!", "full_name": "Test User"}'

# Test generation
./test-generation-fix.sh
```

## 🐳 Docker Deployment

```bash
# Build image
docker build -t velro-backend .

# Run container
docker run -p 8080:8080 \
  --env-file .env \
  velro-backend
```

## 🚂 Railway Deployment

The backend automatically deploys to Railway on push to main branch.

```bash
# Manual deployment (if needed)
railway link
railway up

# View logs
railway logs
```

## 🔍 Recent Updates (January 2025)

### Fixed Issues
- ✅ **422 Error Fix**: Strict parameter validation for model-specific params
- ✅ **Redis Connection**: Fixed internal DNS for Railway deployment
- ✅ **Supabase Auth**: Updated service role keys
- ✅ **Async Architecture**: Non-blocking FAL.ai integration
- ✅ **Git Submodules**: Converted to regular folders for Railway

### Performance Improvements
- Response time: <50ms for auth endpoints
- Concurrent users: 100+ supported
- Cache hit rate: 30-40% with Redis
- Queue management: Instant response with position tracking

## 📊 Monitoring

### Health Checks
- `GET /health` - Service health
- `GET /__version` - Version info
- `GET /api/v1/generations/async/metrics/system` - System metrics

### Logs
```bash
# View Railway logs
railway logs --service velro-backend

# Local logs
tail -f logs/app.log
```

## 🐛 Troubleshooting

### Common Issues

1. **503 Service Unavailable on Registration**
   - Check SUPABASE_SERVICE_ROLE_KEY is valid
   - Verify Supabase project is active

2. **422 Unprocessable Entity on Generation**
   - Fixed: Backend now filters invalid parameters
   - Ensure model_id exists in fal_config.py

3. **Redis Connection Failed**
   - Check REDIS_URL uses internal Railway DNS
   - Format: `redis://default:password@velro-redis.railway.internal:6379`

4. **FAL.ai Rate Limiting**
   - Implement retry logic with exponential backoff
   - Check FAL_KEY is valid

## 📝 API Documentation

Interactive API documentation available at:
- Local: http://localhost:8000/docs
- Production: https://velro-backend-production.up.railway.app/docs

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

Private repository - All rights reserved

---

**Last Updated**: January 2025  
**Version**: 2.0.0 (Async Architecture)  
**Status**: ✅ Production Ready