# Local Visual Generation Testing Guide

## Quick Setup for Testing Visual Generation

### 1. Get Your FAL.ai API Key
1. Go to https://fal.ai/dashboard/keys
2. Create a new API key
3. Copy the key

### 2. Update Environment Variables
```bash
# Edit velro-backend/.env and replace:
FAL_KEY=your_real_fal_key_here
```

### 3. Test Visual Generation
```bash
# Test 1: Direct FAL API test
python3 test_visual_generation.py

# Test 2: Test with real Supabase (optional)
# Update these in .env:
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_key
DEVELOPMENT_MODE=false
```

### 4. Test the Full Stack
```bash
# Terminal 1: Start backend
cd velro-backend
python3 main.py

# Terminal 2: Start frontend
cd velro-frontend
npm run dev

# Open browser: http://localhost:3000
```

### 5. Available Test Models
- **fal-ai/flux-realism** - Photorealistic images
- **fal-ai/flux/dev** - High-quality creative images
- **fal-ai/stable-diffusion-xl** - Stable Diffusion XL
- **fal-ai/flux-lora** - Custom LoRA models

### 6. Test Prompts
Try these prompts to test different styles:

**Photorealistic:**
- "A photorealistic image of a vintage red Ferrari on a mountain road at sunset"

**Artistic:**
- "An oil painting of a serene lake with mountains in the background, impressionist style"

**Fantasy:**
- "A fantasy landscape with dragons flying over a medieval castle, epic cinematic lighting"

**Portrait:**
- "A professional headshot of a businesswoman in a modern office setting"

### 7. Model Switching Test
The system supports dynamic model switching. Test with:
- Different aspect ratios (512x512, 1024x1024, 768x1152)
- Various guidance scales (3.5 - 15)
- Different sampling steps (20 - 50)

### 8. Troubleshooting
- **FAL_KEY not working**: Check if key is valid and has credits
- **Images not generating**: Check FAL.ai dashboard for usage limits
- **Backend not starting**: Ensure all environment variables are set correctly

### 9. Testing Commands
```bash
# Test FAL connection only
python3 -c "from services.fal_service import FalService; import asyncio; asyncio.run(FalService().generate_image('test', 'fal-ai/flux-realism', 512, 512, 1))"

# Test specific model
python3 -c "from services.fal_service import FalService; import asyncio; fs = FalService(); result = asyncio.run(fs.generate_image('A cat wearing a tiny hat', 'fal-ai/flux-realism', 512, 512, 1)); print(result.images[0].url)"
