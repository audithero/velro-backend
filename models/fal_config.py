"""
FAL.ai model registry configuration with all supported models.
"""
from typing import Dict, Any, List
from enum import Enum
from pydantic import BaseModel, HttpUrl, Field

class FALModelType(str, Enum):
    """FAL.ai model type enum."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"

class FALModelConfig(BaseModel):
    """FAL.ai model configuration."""
    endpoint: str
    ai_model_type: FALModelType = Field(alias="model_type")
    credits: int
    max_resolution: str
    supported_formats: List[str]
    parameters: Dict[str, Any]
    description: str
    example_params: Dict[str, Any]
    
    model_config = {
        "protected_namespaces": (),
        "populate_by_name": True
    }

# FAL.ai Model Registry - Updated with current working endpoints (Jan 2025)
FAL_MODEL_REGISTRY: Dict[str, FALModelConfig] = {
    # === IMAGE GENERATION MODELS ===
    "fal-ai/flux-pro/v1.1-ultra": FALModelConfig(
        endpoint="fal-ai/flux-pro/v1.1-ultra",
        ai_model_type=FALModelType.IMAGE,
        credits=50,
        max_resolution="2048x2048",
        supported_formats=["jpg", "png", "webp"],
        description="FLUX Pro v1.1 Ultra - Premium quality image generation with exceptional detail",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "image_size": {"type": "string", "default": "landscape_4_3", "enum": ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]},
            "num_images": {"type": "integer", "default": 1, "min": 1, "max": 4},
            "output_format": {"type": "string", "default": "jpeg", "enum": ["jpeg", "png"]},
            "guidance_scale": {"type": "number", "default": 3.5, "min": 1.0, "max": 20.0},
            "num_inference_steps": {"type": "integer", "default": 28, "min": 1, "max": 50},
            "safety_tolerance": {"type": "integer", "default": 2, "min": 1, "max": 6}
        },
        example_params={
            "prompt": "A futuristic cityscape at sunset with flying cars",
            "image_size": "landscape_4_3",
            "num_images": 1,
            "output_format": "jpeg",
            "guidance_scale": 3.5
        }
    ),
    
    "fal-ai/flux-pro/kontext/max": FALModelConfig(
        endpoint="fal-ai/flux-pro/kontext/max",
        ai_model_type=FALModelType.IMAGE,
        credits=60,
        max_resolution="2048x2048",
        supported_formats=["jpg", "png"],
        description="FLUX Pro Kontext Max - Advanced image generation with context understanding",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "image_size": {"type": "string", "default": "landscape_4_3", "enum": ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]},
            "num_images": {"type": "integer", "default": 1, "min": 1, "max": 4},
            "output_format": {"type": "string", "default": "jpeg", "enum": ["jpeg", "png"]},
            "guidance_scale": {"type": "number", "default": 3.5, "min": 1.0, "max": 20.0},
            "num_inference_steps": {"type": "integer", "default": 28, "min": 1, "max": 50},
            "safety_tolerance": {"type": "integer", "default": 2, "min": 1, "max": 6}
        },
        example_params={
            "prompt": "A professional headshot of a business person",
            "image_size": "portrait_4_3",
            "num_images": 1,
            "output_format": "jpeg",
            "guidance_scale": 3.5
        }
    ),
    
    "fal-ai/imagen4/preview/ultra": FALModelConfig(
        endpoint="fal-ai/imagen4/preview/ultra",
        ai_model_type=FALModelType.IMAGE,
        credits=45,
        max_resolution="2048x2048",
        supported_formats=["jpg", "png"],
        description="Google Imagen 4 Ultra - Advanced photorealistic image generation",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "image_size": {"type": "string", "default": "landscape_4_3", "enum": ["square_hd", "square", "portrait_4_3", "portrait_16_9", "landscape_4_3", "landscape_16_9"]},
            "num_images": {"type": "integer", "default": 1, "min": 1, "max": 4},
            "output_format": {"type": "string", "default": "jpeg", "enum": ["jpeg", "png"]},
            "safety_tolerance": {"type": "integer", "default": 2, "min": 1, "max": 6}
        },
        example_params={
            "prompt": "A serene mountain lake with reflection",
            "image_size": "landscape_16_9",
            "num_images": 1,
            "output_format": "jpeg"
        }
    ),
    
    # === VIDEO GENERATION MODELS ===
    "fal-ai/veo3": FALModelConfig(
        endpoint="fal-ai/veo3",
        ai_model_type=FALModelType.VIDEO,
        credits=500,
        max_resolution="1280x720",
        supported_formats=["mp4"],
        description="Google Veo 3 - Advanced video generation with realistic motion and coherent storytelling",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "duration": {"type": "number", "default": 5.0, "min": 1.0, "max": 10.0},
            "aspect_ratio": {"type": "string", "default": "16:9", "enum": ["16:9", "9:16", "1:1"]},
            "quality": {"type": "string", "default": "high", "enum": ["medium", "high"]},
            "enable_prompt_expansion": {"type": "boolean", "default": True}
        },
        example_params={
            "prompt": "A cat walking through a garden with blooming flowers",
            "duration": 5.0,
            "aspect_ratio": "16:9",
            "quality": "high"
        }
    ),
    
    "fal-ai/minimax/hailuo-02/pro/text-to-video": FALModelConfig(
        endpoint="fal-ai/minimax/hailuo-02/pro/text-to-video",
        ai_model_type=FALModelType.VIDEO,
        credits=400,
        max_resolution="1280x720",
        supported_formats=["mp4"],
        description="Minimax Hailuo 02 Pro - High-quality text-to-video generation",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "duration": {"type": "number", "default": 6.0, "min": 1.0, "max": 10.0},
            "aspect_ratio": {"type": "string", "default": "16:9", "enum": ["16:9", "9:16", "1:1"]},
            "fps": {"type": "integer", "default": 25, "enum": [24, 25, 30]},
            "quality": {"type": "string", "default": "high", "enum": ["low", "medium", "high"]}
        },
        example_params={
            "prompt": "A peaceful mountain landscape with flowing water",
            "duration": 6.0,
            "aspect_ratio": "16:9",
            "fps": 25,
            "quality": "high"
        }
    ),
    
    "fal-ai/kling-video/v2.1/master/text-to-video": FALModelConfig(
        endpoint="fal-ai/kling-video/v2.1/master/text-to-video",
        ai_model_type=FALModelType.VIDEO,
        credits=350,
        max_resolution="1280x720",
        supported_formats=["mp4"],
        description="Kling Video v2.1 Master - Advanced text-to-video generation",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "duration": {"type": "number", "default": 5.0, "min": 1.0, "max": 10.0},
            "aspect_ratio": {"type": "string", "default": "16:9", "enum": ["16:9", "9:16", "1:1"]},
            "creativity": {"type": "number", "default": 0.7, "min": 0.0, "max": 1.0},
            "camera_motion": {"type": "string", "default": "none", "enum": ["none", "horizontal", "vertical", "zoom", "pan"]}
        },
        example_params={
            "prompt": "A drone flying over a mountain landscape",
            "duration": 5.0,
            "aspect_ratio": "16:9",
            "camera_motion": "pan",
            "creativity": 0.7
        }
    ),
    
    "fal-ai/wan-pro/text-to-video": FALModelConfig(
        endpoint="fal-ai/wan-pro/text-to-video",
        ai_model_type=FALModelType.VIDEO,
        credits=300,
        max_resolution="1280x720",
        supported_formats=["mp4"],
        description="Wan Pro - Professional text-to-video generation",
        parameters={
            "prompt": {"type": "string", "required": True, "max_length": 2000},
            "duration": {"type": "number", "default": 5.0, "min": 1.0, "max": 10.0},
            "aspect_ratio": {"type": "string", "default": "16:9", "enum": ["16:9", "9:16", "1:1"]},
            "quality": {"type": "string", "default": "high", "enum": ["medium", "high"]}
        },
        example_params={
            "prompt": "A time-lapse of clouds moving across the sky",
            "duration": 5.0,
            "aspect_ratio": "16:9",
            "quality": "high"
        }
    )
    
    # Note: Old models removed as they are no longer available on FAL.ai
    # - fal-ai/flux-dev (404 error)
    # - fal-ai/flux-schnell (404 error)  
    # - fal-ai/kling-video (replaced with v2.1/master endpoints)
    # - fal-ai/runway-gen3 (no longer available)
    # - fal-ai/luma-dream-machine (no longer available)
    # - fal-ai/stable-cascade (no longer available)
    # - fal-ai/aura-flow (no longer available)
}

def get_model_config(model_id: str) -> FALModelConfig:
    """Get FAL.ai model configuration by model ID."""
    if model_id not in FAL_MODEL_REGISTRY:
        raise ValueError(f"Model {model_id} not found in registry")
    return FAL_MODEL_REGISTRY[model_id]

def get_all_models() -> Dict[str, FALModelConfig]:
    """Get all available FAL.ai models."""
    return FAL_MODEL_REGISTRY

def get_models_by_type(model_type: FALModelType) -> Dict[str, FALModelConfig]:
    """Get models filtered by type."""
    return {
        model_id: config 
        for model_id, config in FAL_MODEL_REGISTRY.items() 
        if config.ai_model_type == model_type
    }

def validate_model_parameters(model_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters against model configuration."""
    config = get_model_config(model_id)
    validated_params = {}
    
    for param_name, param_config in config.parameters.items():
        if param_name in parameters:
            value = parameters[param_name]
            # Basic validation - in production, implement proper validation
            validated_params[param_name] = value
        elif param_config.get("required", False):
            raise ValueError(f"Required parameter '{param_name}' missing for model {model_id}")
        elif "default" in param_config:
            validated_params[param_name] = param_config["default"]
    
    return validated_params