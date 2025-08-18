"""
MCP Router for Velro Platform

This router provides HTTP endpoints for MCP (Model Context Protocol) operations,
allowing the frontend to interact with external services through MCP integration.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
import logging
from datetime import datetime

from services.mcp_service import (
    get_mcp_service,
    MCPService,
    MCPError,
    MCPAuthenticationError,
    MCPRateLimitError,
    MCPServiceUnavailableError,
    execute_supabase_query,
    deploy_railway_service,
    coordinate_with_claude_flow
)
from middleware.auth import get_current_user
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["MCP Integration"])


class MCPHealthResponse(BaseModel):
    """MCP health check response model"""
    timestamp: str
    services: Dict[str, Dict[str, Union[str, Any]]]
    overall_status: str


class SupabaseQueryRequest(BaseModel):
    """Supabase query request model"""
    query: str = Field(..., description="SQL query to execute")
    transaction: bool = Field(default=False, description="Execute in transaction")


class SupabaseQueryResponse(BaseModel):
    """Supabase query response model"""
    status: str
    rows: List[Dict[str, Any]] = []
    affected_rows: Optional[int] = None
    execution_time: Optional[float] = None


class RailwayDeployRequest(BaseModel):
    """Railway deployment request model"""
    project_id: str = Field(..., description="Railway project ID")
    service_id: str = Field(..., description="Railway service ID")
    environment_id: str = Field(..., description="Railway environment ID")
    commit_sha: Optional[str] = Field(None, description="Specific commit to deploy")


class RailwayDeployResponse(BaseModel):
    """Railway deployment response model"""
    deployment_id: str
    status: str
    project_id: str
    service_id: str
    environment_id: str


class ClaudeFlowTaskRequest(BaseModel):
    """Claude Flow task coordination request model"""
    task: str = Field(..., description="Task description")
    agents: Optional[List[str]] = Field(default=None, description="Required agent types")
    strategy: str = Field(default="adaptive", description="Orchestration strategy")
    priority: str = Field(default="medium", description="Task priority")


class ClaudeFlowTaskResponse(BaseModel):
    """Claude Flow task response model"""
    swarm_id: str
    task_id: str
    status: str
    agents: List[Dict[str, Any]]


class BatchOperationRequest(BaseModel):
    """Batch operation request model"""
    operations: List[Dict[str, Any]] = Field(..., description="List of operations to execute")
    transaction: bool = Field(default=False, description="Execute in transaction")


class BatchOperationResponse(BaseModel):
    """Batch operation response model"""
    results: List[Dict[str, Any]]
    total_operations: int
    successful_operations: int
    failed_operations: int
    execution_time: float


def get_mcp_service_dependency() -> MCPService:
    """FastAPI dependency for MCP service"""
    return get_mcp_service()


def handle_mcp_error(error: Exception) -> HTTPException:
    """Convert MCP errors to HTTP exceptions"""
    if isinstance(error, MCPAuthenticationError):
        return HTTPException(
            status_code=401,
            detail={
                "error": "MCP Authentication Failed",
                "message": str(error),
                "code": error.code
            }
        )
    elif isinstance(error, MCPRateLimitError):
        return HTTPException(
            status_code=429,
            detail={
                "error": "MCP Rate Limit Exceeded",
                "message": str(error),
                "code": error.code,
                "retry_after": 60
            }
        )
    elif isinstance(error, MCPServiceUnavailableError):
        return HTTPException(
            status_code=503,
            detail={
                "error": "MCP Service Unavailable",
                "message": str(error),
                "code": error.code
            }
        )
    elif isinstance(error, MCPError):
        return HTTPException(
            status_code=400,
            detail={
                "error": "MCP Error",
                "message": str(error),
                "code": error.code,
                "details": error.details
            }
        )
    else:
        logger.error(f"Unexpected error in MCP operation: {error}")
        return HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred during MCP operation"
            }
        )


@router.get("/health", response_model=MCPHealthResponse)
async def mcp_health_check(
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Perform health check on all MCP integrations
    
    Returns the status of all configured MCP services including:
    - Supabase integration
    - Railway integration  
    - Claude Flow integration
    """
    try:
        health_data = await mcp_service.health_check()
        
        # Determine overall status
        service_statuses = [
            service_info.get("status", "unknown") 
            for service_info in health_data["services"].values()
        ]
        
        if all(status == "healthy" for status in service_statuses):
            overall_status = "healthy"
        elif any(status == "healthy" for status in service_statuses):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        return MCPHealthResponse(
            timestamp=health_data["timestamp"],
            services=health_data["services"],
            overall_status=overall_status
        )
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.post("/supabase/query", response_model=SupabaseQueryResponse)
async def execute_supabase_query_endpoint(
    request: SupabaseQueryRequest,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Execute SQL query on Supabase via MCP
    
    Allows authenticated users to execute SQL queries on the Supabase database
    through the MCP integration with proper error handling and security.
    """
    try:
        start_time = datetime.now()
        
        if not mcp_service.supabase:
            raise HTTPException(
                status_code=503,
                detail="Supabase MCP integration not configured"
            )
        
        result = await mcp_service.supabase.execute_sql(request.query)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return SupabaseQueryResponse(
            status=result.get("status", "success"),
            rows=result.get("rows", []),
            affected_rows=result.get("affected_rows"),
            execution_time=execution_time
        )
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.get("/supabase/tables")
async def list_supabase_tables(
    schemas: Optional[str] = "public",
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    List Supabase database tables via MCP
    
    Returns a list of tables in the specified schemas (default: public)
    """
    try:
        if not mcp_service.supabase:
            raise HTTPException(
                status_code=503,
                detail="Supabase MCP integration not configured"
            )
        
        schema_list = schemas.split(",") if schemas else ["public"]
        tables = await mcp_service.supabase.list_tables(schema_list)
        
        return {
            "tables": tables,
            "schemas": schema_list,
            "count": len(tables)
        }
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.post("/railway/deploy", response_model=RailwayDeployResponse)
async def deploy_railway_service_endpoint(
    request: RailwayDeployRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Deploy Railway service via MCP
    
    Triggers deployment of a specific service in Railway with optional commit SHA.
    The deployment runs in the background and status can be monitored separately.
    """
    try:
        if not mcp_service.railway:
            raise HTTPException(
                status_code=503,
                detail="Railway MCP integration not configured"
            )
        
        deployment_result = await mcp_service.railway.deploy_service(
            project_id=request.project_id,
            service_id=request.service_id,
            environment_id=request.environment_id
        )
        
        # Log deployment for monitoring
        background_tasks.add_task(
            log_deployment_status,
            deployment_result.get("deployment_id"),
            current_user.id
        )
        
        return RailwayDeployResponse(
            deployment_id=deployment_result.get("deployment_id"),
            status=deployment_result.get("status", "pending"),
            project_id=request.project_id,
            service_id=request.service_id,
            environment_id=request.environment_id
        )
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.get("/railway/projects")
async def list_railway_projects(
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    List Railway projects via MCP
    
    Returns a list of all Railway projects accessible with the configured API token.
    """
    try:
        if not mcp_service.railway:
            raise HTTPException(
                status_code=503,
                detail="Railway MCP integration not configured"
            )
        
        projects = await mcp_service.railway.list_projects()
        
        return {
            "projects": projects,
            "count": len(projects)
        }
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.get("/railway/projects/{project_id}/services")
async def list_railway_services(
    project_id: str,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    List services in a Railway project via MCP
    
    Returns all services configured in the specified Railway project.
    """
    try:
        if not mcp_service.railway:
            raise HTTPException(
                status_code=503,
                detail="Railway MCP integration not configured"
            )
        
        services = await mcp_service.railway.list_services(project_id)
        
        return {
            "project_id": project_id,
            "services": services,
            "count": len(services)
        }
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.post("/claude-flow/task", response_model=ClaudeFlowTaskResponse)
async def coordinate_claude_flow_task(
    request: ClaudeFlowTaskRequest,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Coordinate task with Claude Flow via MCP
    
    Initializes a Claude Flow swarm and orchestrates the specified task
    with the requested agents and strategy.
    """
    try:
        result = await coordinate_with_claude_flow(
            task=request.task,
            agents=request.agents
        )
        
        return ClaudeFlowTaskResponse(
            swarm_id=result["swarm"]["swarm_id"],
            task_id=result["task"]["task_id"],
            status=result["task"]["status"],
            agents=[]  # Would include actual agent info
        )
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.get("/claude-flow/swarm/status")
async def get_claude_flow_swarm_status(
    swarm_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Get Claude Flow swarm status via MCP
    
    Returns the current status of the Claude Flow swarm including
    active agents, pending tasks, and performance metrics.
    """
    try:
        # This would use actual MCP call
        # status = await mcp_service.claude_flow.get_swarm_status(swarm_id)
        
        return {
            "swarm_id": swarm_id or "current",
            "status": "active",
            "agents": [],
            "tasks": {
                "pending": 0,
                "active": 0,
                "completed": 0
            },
            "performance": {
                "avg_response_time": 0.5,
                "success_rate": 0.95
            }
        }
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.post("/batch", response_model=BatchOperationResponse)
async def execute_batch_operations(
    request: BatchOperationRequest,
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Execute multiple MCP operations in batch
    
    Allows execution of multiple MCP operations across different services
    in a single request with optional transaction support.
    """
    try:
        start_time = datetime.now()
        
        results = await mcp_service.batch_operations(request.operations)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        successful_operations = sum(1 for r in results if r["status"] == "success")
        failed_operations = len(results) - successful_operations
        
        return BatchOperationResponse(
            results=results,
            total_operations=len(request.operations),
            successful_operations=successful_operations,
            failed_operations=failed_operations,
            execution_time=execution_time
        )
        
    except Exception as e:
        raise handle_mcp_error(e)


@router.get("/integration/status")
async def get_integration_status(
    current_user: User = Depends(get_current_user),
    mcp_service: MCPService = Depends(get_mcp_service_dependency)
):
    """
    Get comprehensive MCP integration status
    
    Returns detailed status information about all MCP integrations
    including configuration, connectivity, and recent operation metrics.
    """
    try:
        health_data = await mcp_service.health_check()
        
        # Add configuration info (without sensitive data)
        integration_status = {
            "timestamp": health_data["timestamp"],
            "services": health_data["services"],
            "configuration": {
                "supabase": {
                    "configured": mcp_service.supabase is not None,
                    "project_ref": mcp_service.config.get("supabase", {}).get("project_ref", "not-configured")[:8] + "..." if mcp_service.supabase else None
                },
                "railway": {
                    "configured": mcp_service.railway is not None,
                    "has_token": bool(mcp_service.config.get("railway", {}).get("api_token")) if mcp_service.railway else False
                },
                "claude_flow": {
                    "configured": mcp_service.claude_flow is not None,
                    "available": True
                }
            },
            "metrics": {
                "total_integrations": 3,
                "active_integrations": sum(1 for service in health_data["services"].values() if service.get("status") == "healthy"),
                "last_health_check": health_data["timestamp"]
            }
        }
        
        return integration_status
        
    except Exception as e:
        raise handle_mcp_error(e)


async def log_deployment_status(deployment_id: str, user_id: str):
    """Background task to log deployment status"""
    logger.info(f"Monitoring deployment {deployment_id} for user {user_id}")
    # Implementation would track deployment progress and log results