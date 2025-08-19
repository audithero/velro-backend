"""
Simple models router with hardcoded fallback - no complex imports.
"""
from fastapi import APIRouter
from typing import Optional

router = APIRouter(tags=["models"])

# Hardcoded fallback models
FALLBACK_MODELS = [
    {
        "model_id": "fal-ai/flux-pro/v1.1-ultra",
        "name": "Flux Pro Ultra",
        "type": "image",
        "credits": 50,
        "description": "Premium quality image generation",
        "is_active": True
    },
    {
        "model_id": "fal-ai/flux/dev",
        "name": "Flux Dev",
        "type": "image",
        "credits": 10,
        "description": "Fast development image generation",
        "is_active": True
    },
    {
        "model_id": "fal-ai/sdxl-lightning-4step",
        "name": "SDXL Lightning",
        "type": "image",
        "credits": 5,
        "description": "Ultra-fast image generation",
        "is_active": True
    }
]

@router.get("/supported")
def get_supported_models(model_type: Optional[str] = None):
    """Get list of supported models - bulletproof version that never 500s."""
    
    # Try to get real models first
    try:
        # Move import inside to avoid startup failures
        import logging
        import traceback
        
        try:
            from models.fal_config import get_all_models
            fal_models = get_all_models()
            
            if fal_models:
                models = []
                for model_id, config in fal_models.items():
                    try:
                        models.append({
                            "model_id": model_id,
                            "name": model_id.replace("fal-ai/", "").replace("-", " ").title(),
                            "type": getattr(config, 'ai_model_type', 'image').value if hasattr(config, 'ai_model_type') else 'image',
                            "credits": getattr(config, 'credits', 10),
                            "description": getattr(config, 'description', 'AI generation model'),
                            "is_active": True
                        })
                    except:
                        pass  # Skip malformed models
                
                if models:
                    if model_type:
                        models = [m for m in models if m["type"] == model_type.lower()]
                    return {"models": models, "count": len(models), "source": "fal"}
        except Exception as e:
            logging.error(f"MODELS IMPORT ERROR:\n{traceback.format_exc()}")
    except:
        pass  # Silently fall through to fallback
    
    # Always return fallback if anything goes wrong
    if model_type:
        filtered = [m for m in FALLBACK_MODELS if m["type"] == model_type.lower()]
        return {"models": filtered, "count": len(filtered), "source": "fallback"}
    
    return {"models": FALLBACK_MODELS, "count": len(FALLBACK_MODELS), "source": "fallback"}