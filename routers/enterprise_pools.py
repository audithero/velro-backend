"""
PHASE 2: Enterprise Connection Pool API Endpoints
Provides monitoring, metrics, and management endpoints for the 6 specialized connection pools.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from utils.auth_system import get_current_user
from database import (
    get_enterprise_pool_metrics,
    enterprise_health_check,
    initialize_enterprise_pools,
    ENTERPRISE_POOLS_AVAILABLE
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/enterprise-pools",
    tags=["Enterprise Connection Pools"],
    responses={
        404: {"description": "Enterprise pools not available"},
        500: {"description": "Internal server error"}
    }
)


@router.get("/health", summary="Enterprise Pool Health Check")
async def pool_health_check():
    """
    Get comprehensive health status of all enterprise connection pools.
    
    Returns:
        - Overall health status
        - Individual pool health
        - Connection metrics
        - Performance indicators
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            raise HTTPException(
                status_code=404, 
                detail="Enterprise connection pools are not available"
            )
        
        health_data = await enterprise_health_check()
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "health": health_data,
            "message": "Enterprise pool health check completed"
        }
        
    except Exception as e:
        logger.error(f"❌ Enterprise pool health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/metrics", summary="Enterprise Pool Metrics")
async def get_pool_metrics():
    """
    Get comprehensive performance metrics from all enterprise connection pools.
    
    Returns detailed metrics including:
    - Connection utilization
    - Query performance statistics
    - Error rates and circuit breaker status
    - Throughput metrics
    - Health indicators
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            raise HTTPException(
                status_code=404,
                detail="Enterprise connection pools are not available"
            )
        
        metrics = await get_enterprise_pool_metrics()
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
            "message": "Enterprise pool metrics retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Enterprise pool metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics retrieval failed: {str(e)}")


@router.get("/metrics/summary", summary="Pool Metrics Summary")
async def get_metrics_summary():
    """
    Get summarized metrics from all enterprise pools for dashboard display.
    
    Returns:
        High-level summary metrics suitable for monitoring dashboards
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            return {
                "status": "unavailable",
                "message": "Enterprise connection pools are not available"
            }
        
        metrics = await get_enterprise_pool_metrics()
        
        if metrics.get("status") != "initialized":
            return {
                "status": "not_initialized",
                "message": "Enterprise pools not initialized yet"
            }
        
        summary = metrics.get("summary", {})
        
        # Calculate key performance indicators
        connection_utilization = summary.get("connection_utilization_percent", 0)
        health_score = (summary.get("healthy_pools", 0) / max(summary.get("total_pools", 1), 1)) * 100
        
        # Performance status
        performance_status = "excellent"
        if connection_utilization > 80:
            performance_status = "high_load"
        elif connection_utilization > 60:
            performance_status = "moderate_load"
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "overall_health": metrics.get("overall_health", "unknown"),
                "health_score_percent": round(health_score, 1),
                "performance_status": performance_status,
                "total_pools": summary.get("total_pools", 0),
                "healthy_pools": summary.get("healthy_pools", 0),
                "total_connections": summary.get("total_connections", 0),
                "active_connections": summary.get("active_connections", 0),
                "connection_utilization_percent": round(connection_utilization, 1),
                "total_queries_executed": summary.get("total_queries_executed", 0),
                "target_compliance": metrics.get("target_compliance", {}),
                "performance_targets": metrics.get("performance_targets", {})
            },
            "message": "Pool metrics summary retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ Pool metrics summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Summary retrieval failed: {str(e)}")


@router.get("/pools/{pool_type}/metrics", summary="Individual Pool Metrics")
async def get_individual_pool_metrics(pool_type: str):
    """
    Get detailed metrics for a specific connection pool.
    
    Args:
        pool_type: Type of pool (auth, read, write, analytics, admin, batch)
    
    Returns:
        Detailed metrics for the specified pool
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            raise HTTPException(
                status_code=404,
                detail="Enterprise connection pools are not available"
            )
        
        # Validate pool type
        valid_pool_types = ["auth", "read", "write", "analytics", "admin", "batch"]
        if pool_type not in valid_pool_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pool type. Must be one of: {', '.join(valid_pool_types)}"
            )
        
        metrics = await get_enterprise_pool_metrics()
        pools = metrics.get("pools", {})
        
        pool_key = f"{pool_type}_pool"
        if pool_key not in pools:
            raise HTTPException(
                status_code=404,
                detail=f"Pool '{pool_type}' not found or not initialized"
            )
        
        pool_metrics = pools[pool_key]
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "pool_type": pool_type,
            "metrics": pool_metrics,
            "message": f"Metrics for {pool_type} pool retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Individual pool metrics failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pool metrics retrieval failed: {str(e)}")


@router.get("/status", summary="Enterprise Pool Status")
async def get_pool_status():
    """
    Get current status and configuration of the enterprise pool system.
    
    Returns:
        - System availability
        - Configuration details
        - Pool initialization status
        - Feature flags
    """
    try:
        status_info = {
            "enterprise_pools_available": ENTERPRISE_POOLS_AVAILABLE,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if not ENTERPRISE_POOLS_AVAILABLE:
            status_info.update({
                "status": "unavailable",
                "message": "Enterprise connection pools are not available in this deployment",
                "recommendation": "Install asyncpg dependency and ensure PostgreSQL connectivity"
            })
            return status_info
        
        # Get current metrics to determine initialization status
        metrics = await get_enterprise_pool_metrics()
        
        status_info.update({
            "status": metrics.get("status", "unknown"),
            "message": "Enterprise connection pools are available",
            "initialization_status": "initialized" if metrics.get("status") == "initialized" else "not_initialized",
            "pool_configuration": {
                "total_pool_types": 6,
                "pool_types": ["auth", "read", "write", "analytics", "admin", "batch"],
                "features": {
                    "health_monitoring": True,
                    "circuit_breaker": True,
                    "performance_monitoring": True,
                    "query_routing": True,
                    "failover_support": True,
                    "metrics_collection": True
                }
            }
        })
        
        if metrics.get("status") == "initialized":
            summary = metrics.get("summary", {})
            status_info["current_state"] = {
                "total_pools": summary.get("total_pools", 0),
                "healthy_pools": summary.get("healthy_pools", 0),
                "total_connections": summary.get("total_connections", 0),
                "active_connections": summary.get("active_connections", 0)
            }
        
        return status_info
        
    except Exception as e:
        logger.error(f"❌ Pool status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@router.post("/initialize", summary="Initialize Enterprise Pools")
async def initialize_pools(current_user: dict = Depends(get_current_user)):
    """
    Initialize the enterprise connection pool system.
    
    Requires authentication. This endpoint is typically called during application startup
    but can be used to reinitialize pools if needed.
    
    Returns:
        Initialization status and result
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            raise HTTPException(
                status_code=404,
                detail="Enterprise connection pools are not available"
            )
        
        logger.info(f"🔄 Pool initialization requested by user: {current_user.get('id', 'unknown')}")
        
        # Attempt to initialize pools
        success = await initialize_enterprise_pools()
        
        if success:
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Enterprise connection pools initialized successfully",
                "initiated_by": current_user.get("email", "unknown user")
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Enterprise pool initialization failed"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Pool initialization failed: {e}")
        raise HTTPException(status_code=500, detail=f"Initialization failed: {str(e)}")


@router.get("/performance-targets", summary="Performance Targets")
async def get_performance_targets():
    """
    Get the performance targets and current compliance status.
    
    Returns:
        - Performance targets as defined in PRD
        - Current compliance status
        - Recommendations for optimization
    """
    try:
        if not ENTERPRISE_POOLS_AVAILABLE:
            raise HTTPException(
                status_code=404,
                detail="Enterprise connection pools are not available"
            )
        
        metrics = await get_enterprise_pool_metrics()
        
        if metrics.get("status") != "initialized":
            return {
                "status": "not_initialized",
                "message": "Enterprise pools not initialized - targets not available"
            }
        
        targets = metrics.get("performance_targets", {})
        compliance = metrics.get("target_compliance", {})
        
        # Generate recommendations based on compliance
        recommendations = []
        
        for target_name, compliance_data in compliance.items():
            if isinstance(compliance_data, dict) and not compliance_data.get("compliant", True):
                if "latency" in target_name:
                    recommendations.append(f"Consider optimizing {target_name} - current performance below target")
                elif "connections" in target_name:
                    recommendations.append(f"Consider scaling {target_name} - may need more connections")
                elif "success_rate" in target_name:
                    recommendations.append(f"Investigate error causes affecting {target_name}")
        
        if not recommendations:
            recommendations.append("All performance targets are being met - system operating optimally")
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "performance_targets": targets,
            "compliance_status": compliance,
            "recommendations": recommendations,
            "message": "Performance targets and compliance status retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Performance targets retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Performance targets retrieval failed: {str(e)}")


@router.get("/documentation", summary="Enterprise Pool Documentation")
async def get_documentation():
    """
    Get comprehensive documentation for the enterprise connection pool system.
    
    Returns:
        - Architecture overview
        - Pool specifications
        - Performance characteristics
        - Usage guidelines
    """
    return {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat(),
        "documentation": {
            "overview": {
                "title": "Enterprise Connection Pool System - Phase 2",
                "description": "6 specialized connection pools optimized for different workloads",
                "version": "2.0",
                "target_users": "10,000+ concurrent users",
                "total_connections": "200+ connections across all pools"
            },
            "pools": {
                "auth_pool": {
                    "purpose": "Authentication operations",
                    "connections": "10-50 connections",
                    "optimized_for": "Fast, frequent auth queries",
                    "target_latency": "<50ms",
                    "use_cases": ["user login", "token validation", "permission checks"]
                },
                "read_pool": {
                    "purpose": "Read operations",
                    "connections": "20-75 connections",
                    "optimized_for": "Complex read queries",
                    "target_latency": "<200ms",
                    "use_cases": ["user data retrieval", "project listings", "search queries"]
                },
                "write_pool": {
                    "purpose": "Write operations",
                    "connections": "5-25 connections",
                    "optimized_for": "ACID compliance and durability",
                    "target_latency": "<500ms",
                    "use_cases": ["data creation", "updates", "transactions"]
                },
                "analytics_pool": {
                    "purpose": "Analytics queries",
                    "connections": "5-20 connections",
                    "optimized_for": "Heavy analytical queries",
                    "target_latency": "<5s",
                    "use_cases": ["reporting", "aggregations", "business intelligence"]
                },
                "admin_pool": {
                    "purpose": "Administrative operations",
                    "connections": "2-10 connections",
                    "optimized_for": "DDL and maintenance operations",
                    "target_latency": "<10s",
                    "use_cases": ["schema changes", "maintenance", "admin operations"]
                },
                "batch_pool": {
                    "purpose": "Batch operations",
                    "connections": "5-30 connections",
                    "optimized_for": "Bulk operations and high throughput",
                    "target_latency": "<30s",
                    "use_cases": ["data imports", "bulk processing", "migration tasks"]
                }
            },
            "features": {
                "health_monitoring": "Real-time pool health tracking with status indicators",
                "circuit_breaker": "Automatic failover protection with configurable thresholds",
                "performance_monitoring": "Comprehensive metrics collection and analysis",
                "query_routing": "Intelligent routing based on query type and characteristics",
                "failover_support": "Automatic failover between pools for high availability",
                "connection_pooling": "Advanced connection lifecycle management"
            },
            "api_endpoints": {
                "health": "GET /enterprise-pools/health - Pool health status",
                "metrics": "GET /enterprise-pools/metrics - Detailed metrics",
                "summary": "GET /enterprise-pools/metrics/summary - Dashboard summary",
                "individual": "GET /enterprise-pools/pools/{type}/metrics - Individual pool metrics",
                "status": "GET /enterprise-pools/status - System status",
                "initialize": "POST /enterprise-pools/initialize - Initialize pools",
                "targets": "GET /enterprise-pools/performance-targets - Performance targets",
                "documentation": "GET /enterprise-pools/documentation - This documentation"
            },
            "configuration": {
                "environment_variables": {
                    "AUTH_POOL_MIN_CONNECTIONS": "Minimum connections for auth pool (default: 10)",
                    "AUTH_POOL_MAX_CONNECTIONS": "Maximum connections for auth pool (default: 50)",
                    "READ_POOL_MIN_CONNECTIONS": "Minimum connections for read pool (default: 20)",
                    "READ_POOL_MAX_CONNECTIONS": "Maximum connections for read pool (default: 75)",
                    "WRITE_POOL_MIN_CONNECTIONS": "Minimum connections for write pool (default: 5)",
                    "WRITE_POOL_MAX_CONNECTIONS": "Maximum connections for write pool (default: 25)",
                    "ANALYTICS_POOL_MIN_CONNECTIONS": "Minimum connections for analytics pool (default: 5)",
                    "ANALYTICS_POOL_MAX_CONNECTIONS": "Maximum connections for analytics pool (default: 20)",
                    "ADMIN_POOL_MIN_CONNECTIONS": "Minimum connections for admin pool (default: 2)",
                    "ADMIN_POOL_MAX_CONNECTIONS": "Maximum connections for admin pool (default: 10)",
                    "BATCH_POOL_MIN_CONNECTIONS": "Minimum connections for batch pool (default: 5)",
                    "BATCH_POOL_MAX_CONNECTIONS": "Maximum connections for batch pool (default: 30)",
                    "POOL_FAILOVER_ENABLED": "Enable failover between pools (default: true)",
                    "POOL_PERFORMANCE_MONITORING_ENABLED": "Enable performance monitoring (default: true)"
                }
            }
        },
        "message": "Enterprise pool system documentation retrieved successfully"
    }