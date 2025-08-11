"""
Kong API Gateway Proxy Service for Velro AI Platform
Routes external AI API calls through Kong gateway for monitoring, fallback, and security.
Integrates with existing FAL.ai service while adding Kong proxy layer.
Date: August 5, 2025
Author: Kong Integration Specialist
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
import os
import json
import httpx
from datetime import datetime

from config import settings
from models.fal_config import get_model_config, validate_model_parameters, FALModelType
from models.generation import GenerationStatus

logger = logging.getLogger(__name__)


class KongProxyService:
    """Service for routing AI API calls through Kong Gateway."""
    
    def __init__(self):
        # Kong Gateway configuration
        self.kong_gateway_url = os.getenv('KONG_URL', 'https://kong-production.up.railway.app')
        self.kong_admin_url = os.getenv('KONG_ADMIN_URL', 'http://kong:8001')
        self.kong_api_key = os.getenv('KONG_API_KEY', 'velro-backend-key-2025-prod')
        self.enable_kong_proxy = os.getenv('KONG_PROXY_ENABLED', 'true').lower() == 'true'
        
        # Fallback to direct FAL.ai if Kong is disabled
        if not self.enable_kong_proxy:
            logger.warning("⚠️ Kong proxy disabled - falling back to direct FAL.ai integration")
            
        # HTTP client configuration
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0),  # 10 minutes for video generation
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
        
        # Model endpoint mapping for Kong routes
        self.kong_route_mapping = {
            # Image Generation Models
            "fal-ai/flux-pro/v1.1-ultra": "/fal/flux-pro-ultra",
            "fal-ai/flux-pro/kontext/max": "/fal/flux-pro-kontext", 
            "fal-ai/imagen4/preview/ultra": "/fal/imagen4-ultra",
            "fal-ai/flux/dev": "/fal/flux-dev",
            
            # Video Generation Models
            "fal-ai/veo3": "/fal/veo3",
            "fal-ai/minimax/hailuo-02/pro/text-to-video": "/fal/minimax-hailuo",
            "fal-ai/kling-video/v2.1/master/text-to-video": "/fal/kling-video",
            "fal-ai/wan-pro/text-to-video": "/fal/wan-pro",
            
            # Specialized Services  
            "fal-ai/face-swap": "/fal/face-swap",
            "fal-ai/image-enhance": "/fal/image-enhance",
            "fal-ai/audio-generation": "/fal/audio-gen"
        }
        
        # Metrics collection
        self.request_metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_response_time": 0.0,
            "error_counts": {},
            "model_usage": {},
            "last_reset": time.time()
        }
        
        logger.info(f"🚀 Kong Proxy Service initialized")
        logger.info(f"🔗 Kong Gateway URL: {self.kong_gateway_url}")
        logger.info(f"⚙️ Kong Admin URL: {self.kong_admin_url}")
        logger.info(f"🎯 Kong Proxy Enabled: {self.enable_kong_proxy}")
        logger.info(f"🔑 Kong API Key: {self.kong_api_key[:8]}...{self.kong_api_key[-4:] if len(self.kong_api_key) > 12 else 'configured'}")
        
    async def create_generation(
        self,
        model_id: str,
        prompt: str,
        user_id: UUID,
        auth_token: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new generation using Kong Gateway proxy.
        
        Args:
            model_id: FAL.ai model identifier
            prompt: Text prompt for generation
            user_id: User UUID for tracking
            auth_token: JWT token for authentication
            negative_prompt: Optional negative prompt
            reference_image_url: Optional reference image URL
            parameters: Additional model-specific parameters
            
        Returns:
            Generation result with output URLs and metadata
        """
        kong_request_id = str(uuid4())
        start_time = time.time()
        
        try:
            # Get model configuration
            model_config = get_model_config(model_id)
            
            # Check if Kong proxy is enabled
            if not self.enable_kong_proxy:
                logger.info(f"Kong proxy disabled - using direct FAL.ai for {model_id}")
                return await self._direct_fal_generation(
                    model_id, prompt, negative_prompt, reference_image_url, parameters
                )
            
            # Get Kong route for this model
            kong_route = self.kong_route_mapping.get(model_id)
            if not kong_route:
                logger.warning(f"No Kong route found for model {model_id} - falling back to direct")
                return await self._direct_fal_generation(
                    model_id, prompt, negative_prompt, reference_image_url, parameters
                )
            
            # Prepare generation parameters
            generation_params = {
                "prompt": prompt
            }
            
            # Add negative prompt if provided
            if negative_prompt:
                generation_params["negative_prompt"] = negative_prompt
                
            # Add reference image for supported models
            if reference_image_url and "image" in model_config.parameters:
                generation_params["image"] = reference_image_url
            elif reference_image_url and "first_frame_image" in model_config.parameters:
                generation_params["first_frame_image"] = reference_image_url
                
            # Add custom parameters
            if parameters:
                generation_params.update(parameters)
                
            # Validate parameters against model configuration
            validated_params = validate_model_parameters(model_id, generation_params)
            
            # Prepare Kong request headers with API key authentication
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
                "X-API-Key": self.kong_api_key,
                "X-User-ID": str(user_id),
                "X-Kong-Request-ID": kong_request_id,
                "X-Model-ID": model_id,
                "X-Generation-Type": model_config.ai_model_type.value,
                "X-Credits-Cost": str(model_config.credits),
                "User-Agent": "Velro-Backend/1.0"
            }
            
            # Construct Kong proxy URL
            kong_url = f"{self.kong_gateway_url}{kong_route}"
            
            logger.info(f"🚀 Starting Kong proxy generation for {model_id}")
            logger.info(f"🎯 Kong URL: {kong_url}")
            logger.debug(f"📋 Parameters: {validated_params}")
            
            # Make request through Kong Gateway
            response = await self.client.post(
                kong_url,
                json=validated_params,
                headers=headers
            )
            
            generation_time = time.time() - start_time
            
            # Handle Kong response
            if response.status_code == 200:
                result = response.json()
                
                # Extract output URLs based on model type
                output_urls = []
                if "images" in result:
                    output_urls = [img["url"] for img in result["images"]]
                elif "video" in result:
                    output_urls = [result["video"]["url"]]
                elif "image" in result:
                    output_urls = [result["image"]["url"]]
                elif "audio" in result:
                    output_urls = [result["audio"]["url"]]
                
                # Extract Kong headers for monitoring
                kong_headers = {
                    "kong_request_id": response.headers.get("X-Kong-Request-ID", kong_request_id),
                    "kong_proxy_latency": response.headers.get("X-Kong-Proxy-Latency"),
                    "kong_upstream_latency": response.headers.get("X-Kong-Upstream-Latency"),
                    "kong_service": response.headers.get("X-Kong-Service"),
                    "processing_time": response.headers.get("X-Processing-Time")
                }
                
                logger.info(f"✅ Kong proxy generation completed in {generation_time:.2f}s")
                
                # Update internal metrics
                await self._update_request_metrics(
                    success=True,
                    response_time=generation_time,
                    model_id=model_id,
                    status_code=response.status_code
                )
                
                # Store API metrics for analytics
                await self._store_api_metrics(
                    user_id=user_id,
                    model_id=model_id,
                    kong_request_id=kong_request_id,
                    status_code=response.status_code,
                    latency_ms=int(generation_time * 1000),
                    credits_used=model_config.credits,
                    request_size_bytes=len(json.dumps(validated_params)),
                    response_size_bytes=len(response.content),
                    kong_headers=kong_headers
                )
                
                return {
                    "status": GenerationStatus.COMPLETED,
                    "output_urls": output_urls,
                    "metadata": {
                        "generation_time": generation_time,
                        "model_id": model_id,
                        "endpoint": model_config.endpoint,
                        "kong_route": kong_route,
                        "kong_request_id": kong_request_id,
                        "kong_headers": kong_headers,
                        "fal_result": result
                    }
                }
                
            else:
                # Handle Kong/upstream errors
                error_message = f"Kong proxy error: {response.status_code}"
                try:
                    error_detail = response.json()
                    error_message = f"Kong proxy error: {error_detail.get('message', str(error_detail))}"
                except:
                    error_message = f"Kong proxy error: {response.text}"
                
                logger.error(f"❌ Kong proxy failed: {error_message}")
                
                # Update internal metrics
                await self._update_request_metrics(
                    success=False,
                    response_time=generation_time,
                    model_id=model_id,
                    status_code=response.status_code,
                    error_message=error_message
                )
                
                # Store error metrics
                await self._store_api_metrics(
                    user_id=user_id,
                    model_id=model_id,
                    kong_request_id=kong_request_id,
                    status_code=response.status_code,
                    latency_ms=int(generation_time * 1000),
                    credits_used=0,  # No credits charged for failed requests
                    error_message=error_message
                )
                
                # Check if we should fallback to direct FAL.ai
                if response.status_code in [401, 403, 502, 503, 504]:  # Auth and Gateway errors
                    if response.status_code == 401:
                        logger.error(f"❌ Kong authentication failed - check API key configuration")
                    elif response.status_code == 403:
                        logger.error(f"❌ Kong authorization failed - check consumer permissions")
                    
                    logger.warning(f"⚠️ Kong error {response.status_code} - attempting direct fallback")
                    return await self._direct_fal_generation(
                        model_id, prompt, negative_prompt, reference_image_url, parameters
                    )
                
                return {
                    "status": GenerationStatus.FAILED,
                    "error_message": error_message,
                    "output_urls": [],
                    "metadata": {
                        "kong_request_id": kong_request_id,
                        "status_code": response.status_code
                    }
                }
                
        except httpx.TimeoutException:
            generation_time = time.time() - start_time
            logger.error(f"❌ Kong proxy timeout after {generation_time:.2f}s")
            
            await self._store_api_metrics(
                user_id=user_id,
                model_id=model_id,
                kong_request_id=kong_request_id,
                status_code=408,
                latency_ms=int(generation_time * 1000),
                credits_used=0,
                error_message="Request timeout"
            )
            
            return {
                "status": GenerationStatus.FAILED,
                "error_message": "Request timeout - generation took too long",
                "output_urls": [],
                "metadata": {"kong_request_id": kong_request_id}
            }
            
        except Exception as e:
            generation_time = time.time() - start_time
            logger.error(f"❌ Kong proxy service error: {e}")
            
            await self._store_api_metrics(
                user_id=user_id,
                model_id=model_id,
                kong_request_id=kong_request_id,
                status_code=500,
                latency_ms=int(generation_time * 1000),
                credits_used=0,
                error_message=str(e)
            )
            
            # Fallback to direct FAL.ai on service errors
            logger.warning(f"⚠️ Kong service error - attempting direct fallback: {e}")
            return await self._direct_fal_generation(
                model_id, prompt, negative_prompt, reference_image_url, parameters
            )
    
    async def _direct_fal_generation(
        self,
        model_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Fallback to direct FAL.ai integration when Kong is unavailable."""
        try:
            # Import FAL service for direct access
            from services.fal_service import fal_service
            
            result = await fal_service.create_generation(
                model_id=model_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                reference_image_url=reference_image_url,
                parameters=parameters
            )
            
            # Add fallback indicator to metadata
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["fallback_mode"] = "direct_fal"
            result["metadata"]["kong_proxy_used"] = False
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Direct FAL.ai fallback failed: {e}")
            return {
                "status": GenerationStatus.FAILED,
                "error_message": f"Both Kong proxy and direct FAL.ai failed: {str(e)}",
                "output_urls": [],
                "metadata": {"fallback_mode": "failed"}
            }
    
    async def _store_api_metrics(
        self,
        user_id: UUID,
        model_id: str,
        kong_request_id: str,
        status_code: int,
        latency_ms: int,
        credits_used: int,
        request_size_bytes: Optional[int] = None,
        response_size_bytes: Optional[int] = None,
        error_message: Optional[str] = None,
        kong_headers: Optional[Dict[str, Any]] = None
    ):
        """Store API metrics in Supabase for analytics and monitoring."""
        try:
            from database import SupabaseClient
            
            db = SupabaseClient()
            
            metrics_data = {
                "id": str(uuid4()),
                "user_id": str(user_id),
                "model_id": model_id,
                "kong_request_id": kong_request_id,
                "request_timestamp": datetime.utcnow().isoformat(),
                "status_code": status_code,
                "latency_ms": latency_ms,
                "credits_used": credits_used,
                "external_api_provider": "fal-ai",
                "request_size_bytes": request_size_bytes,
                "response_size_bytes": response_size_bytes,
                "error_message": error_message,
                "kong_headers": kong_headers or {},
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Insert metrics into api_metrics table
            result = db.service_client.table("api_metrics").insert(metrics_data).execute()
            
            if result.data:
                logger.debug(f"📊 API metrics stored for request {kong_request_id}")
            else:
                logger.warning(f"⚠️ Failed to store API metrics for request {kong_request_id}")
                
        except Exception as e:
            logger.error(f"❌ Failed to store API metrics: {e}")
            # Don't fail the generation request if metrics storage fails
    
    async def get_kong_health(self) -> Dict[str, Any]:
        """Check Kong Gateway health status."""
        try:
            response = await self.client.get(f"{self.kong_admin_url}/status")
            if response.status_code == 200:
                status_data = response.json()
                return {
                    "kong_status": "healthy",
                    "kong_version": status_data.get("version"),
                    "database": status_data.get("database", {}).get("reachable", False),
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {
                    "kong_status": "unhealthy",
                    "status_code": response.status_code,
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "kong_status": "unavailable",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def get_supported_models(self) -> List[Dict[str, Any]]:
        """Get list of all supported models with Kong routing information."""
        try:
            from models.fal_config import get_all_models
            
            models = []
            registry = get_all_models()
            
            for model_id, config in registry.items():
                kong_route = self.kong_route_mapping.get(model_id)
                
                model_info = {
                    "model_id": model_id,
                    "name": model_id.split('/')[-1].replace('-', ' ').title(),
                    "type": config.ai_model_type.value,
                    "credits": config.credits,
                    "max_resolution": config.max_resolution,
                    "supported_formats": config.supported_formats,
                    "description": config.description,
                    "endpoint": config.endpoint,
                    "kong_route": kong_route,
                    "kong_proxy_available": kong_route is not None and self.enable_kong_proxy,
                    "parameters": config.parameters,
                    "example_params": config.example_params
                }
                models.append(model_info)
            
            # Sort by type and then by credits
            models.sort(key=lambda x: (x["type"], x["credits"]))
            
            logger.info(f"Retrieved {len(models)} supported models with Kong routing")
            return models
            
        except Exception as e:
            logger.error(f"Failed to get supported models: {e}")
            return []
    
    async def get_api_metrics_summary(self, user_id: UUID, hours: int = 24) -> Dict[str, Any]:
        """Get API usage metrics summary for a user."""
        try:
            from database import SupabaseClient
            
            db = SupabaseClient()
            
            # Query metrics from the last N hours
            cutoff_time = datetime.utcnow().replace(microsecond=0) - timedelta(hours=hours)
            
            result = db.service_client.table("api_metrics") \
                .select("*") \
                .eq("user_id", str(user_id)) \
                .gte("request_timestamp", cutoff_time.isoformat()) \
                .execute()
            
            if not result.data:
                return {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "total_credits_used": 0,
                    "average_latency_ms": 0,
                    "most_used_model": None,
                    "time_period_hours": hours
                }
            
            metrics = result.data
            
            successful_requests = [m for m in metrics if 200 <= m["status_code"] < 300]
            failed_requests = [m for m in metrics if m["status_code"] >= 400]
            
            # Calculate model usage
            model_usage = {}
            for metric in metrics:
                model_id = metric["model_id"]
                model_usage[model_id] = model_usage.get(model_id, 0) + 1
            
            most_used_model = max(model_usage.items(), key=lambda x: x[1])[0] if model_usage else None
            
            return {
                "total_requests": len(metrics),
                "successful_requests": len(successful_requests),
                "failed_requests": len(failed_requests),
                "success_rate": len(successful_requests) / len(metrics) if metrics else 0,
                "total_credits_used": sum(m["credits_used"] for m in metrics),
                "average_latency_ms": sum(m["latency_ms"] for m in metrics) / len(metrics) if metrics else 0,
                "most_used_model": most_used_model,
                "model_usage": model_usage,
                "time_period_hours": hours,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get API metrics summary: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _update_request_metrics(
        self,
        success: bool,
        response_time: float,
        model_id: str,
        status_code: int,
        error_message: Optional[str] = None
    ):
        """Update internal request metrics."""
        try:
            self.request_metrics["total_requests"] += 1
            self.request_metrics["total_response_time"] += response_time
            
            if success:
                self.request_metrics["successful_requests"] += 1
            else:
                self.request_metrics["failed_requests"] += 1
                
                # Track error types
                error_key = error_message or f"status_{status_code}"
                self.request_metrics["error_counts"][error_key] = (
                    self.request_metrics["error_counts"].get(error_key, 0) + 1
                )
            
            # Track model usage
            self.request_metrics["model_usage"][model_id] = (
                self.request_metrics["model_usage"].get(model_id, 0) + 1
            )
            
        except Exception as e:
            logger.error(f"Failed to update request metrics: {e}")
    
    async def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive Kong proxy service metrics."""
        try:
            total_requests = self.request_metrics["total_requests"]
            successful_requests = self.request_metrics["successful_requests"]
            failed_requests = self.request_metrics["failed_requests"]
            total_response_time = self.request_metrics["total_response_time"]
            
            avg_response_time = (
                total_response_time / total_requests if total_requests > 0 else 0
            )
            success_rate = (
                successful_requests / total_requests if total_requests > 0 else 0
            )
            error_rate = (
                failed_requests / total_requests if total_requests > 0 else 0
            )
            
            uptime_since_reset = time.time() - self.request_metrics["last_reset"]
            
            return {
                "kong_proxy_metrics": {
                    "enabled": self.enable_kong_proxy,
                    "gateway_url": self.kong_gateway_url,
                    "uptime_seconds": uptime_since_reset,
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "failed_requests": failed_requests,
                    "success_rate": round(success_rate, 4),
                    "error_rate": round(error_rate, 4),
                    "average_response_time_seconds": round(avg_response_time, 3),
                    "requests_per_second": (
                        total_requests / uptime_since_reset if uptime_since_reset > 0 else 0
                    ),
                    "model_usage": self.request_metrics["model_usage"],
                    "error_breakdown": self.request_metrics["error_counts"],
                    "route_mapping_count": len(self.kong_route_mapping),
                    "last_reset": datetime.fromtimestamp(self.request_metrics["last_reset"]).isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate comprehensive metrics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def reset_metrics(self) -> Dict[str, Any]:
        """Reset internal metrics counters."""
        try:
            old_metrics = self.request_metrics.copy()
            
            self.request_metrics = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_response_time": 0.0,
                "error_counts": {},
                "model_usage": {},
                "last_reset": time.time()
            }
            
            logger.info("📊 Kong proxy metrics reset")
            
            return {
                "status": "metrics_reset",
                "previous_metrics": old_metrics,
                "reset_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to reset metrics: {e}")
            return {"error": str(e)}
    
    async def get_service_status(self) -> Dict[str, Any]:
        """Get comprehensive service status including health and metrics."""
        try:
            # Get Kong health
            kong_health = await self.get_kong_health()
            
            # Get comprehensive metrics
            metrics = await self.get_comprehensive_metrics()
            
            # Determine overall service status
            kong_healthy = kong_health.get("kong_status") == "healthy"
            high_error_rate = metrics.get("kong_proxy_metrics", {}).get("error_rate", 0) > 0.1
            
            if not kong_healthy:
                overall_status = "unhealthy"
            elif high_error_rate:
                overall_status = "degraded"
            else:
                overall_status = "healthy"
            
            return {
                "service_status": overall_status,
                "kong_health": kong_health,
                "metrics": metrics,
                "configuration": {
                    "kong_enabled": self.enable_kong_proxy,
                    "gateway_url": self.kong_gateway_url,
                    "admin_url": self.kong_admin_url,
                    "supported_models": len(self.kong_route_mapping)
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return {
                "service_status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()


# Global service instance
kong_proxy_service = KongProxyService()