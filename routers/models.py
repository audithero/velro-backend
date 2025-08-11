"""
AI Models router for listing available models and their configurations.
Following CLAUDE.md: Router layer for API endpoints, using FAL.ai model registry.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

from models.fal_config import get_all_models, get_models_by_type, FALModelType

router = APIRouter(tags=["models"])


@router.get("/")
@router.get("")  # CRITICAL FIX: Add route without trailing slash
async def list_models(
    model_type: Optional[str] = None,
    available_only: bool = True
):
    """List available AI models from FAL.ai registry with optional filtering."""
    try:
        # Get models from FAL.ai registry
        if model_type:
            # Convert string to enum
            try:
                model_type_enum = FALModelType(model_type.lower())
                fal_models = get_models_by_type(model_type_enum)
            except ValueError:
                # Invalid model type, return empty list
                return {"models": []}
        else:
            fal_models = get_all_models()
        
        # Convert FAL.ai models to API response format
        models = []
        for model_id, config in fal_models.items():
            models.append({
                "id": model_id,  # Use actual FAL.ai model ID
                "name": model_id.replace("fal-ai/", "").replace("-", " ").title(),
                "generation_type": config.ai_model_type.value,  # CRITICAL FIX: Use ai_model_type instead of model_type
                "credits_cost": config.credits,
                "description": config.description,
                "parameters": config.parameters,
                "is_active": True  # All models in registry are active
            })
        
        # Filter by availability if requested
        if available_only:
            models = [m for m in models if m["is_active"]]
        
        return {"models": models}
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to list models: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve models")


@router.get("/{model_id}")
async def get_model(model_id: str):
    """Get model configuration by ID from FAL.ai registry."""
    try:
        from models.fal_config import get_model_config
        config = get_model_config(model_id)
        
        return {
            "id": model_id,
            "name": model_id.replace("fal-ai/", "").replace("-", " ").title(),
            "generation_type": config.ai_model_type.value,  # CRITICAL FIX: Use ai_model_type instead of model_type
            "credits_cost": config.credits,
            "description": config.description,
            "parameters": config.parameters,
            "max_resolution": config.max_resolution,
            "supported_formats": config.supported_formats,
            "example_params": config.example_params,
            "is_active": True
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get model {model_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model")


@router.get("/{model_id}/pricing")
async def get_model_pricing(model_id: str):
    """Get pricing information for a model."""
    try:
        from models.fal_config import get_model_config
        config = get_model_config(model_id)
        
        return {
            "model_id": model_id,
            "credits_cost": config.credits,
            "max_resolution": config.max_resolution,
            "supported_formats": config.supported_formats
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get pricing for model {model_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve model pricing")