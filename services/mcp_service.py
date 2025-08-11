"""
MCP Integration Service for Velro Platform

This service provides centralized MCP (Model Context Protocol) integration 
for connecting with external services like Supabase, Railway, and Claude Flow.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
import json
from functools import wraps
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Base exception for MCP-related errors"""
    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class MCPAuthenticationError(MCPError):
    """Authentication-related MCP errors"""
    pass


class MCPRateLimitError(MCPError):
    """Rate limiting errors from MCP services"""
    pass


class MCPServiceUnavailableError(MCPError):
    """Service unavailability errors"""
    pass


def mcp_error_handler(func):
    """Decorator for handling MCP errors gracefully"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except MCPAuthenticationError as e:
            logger.error(f"MCP Authentication error in {func.__name__}: {e}")
            raise
        except MCPRateLimitError as e:
            logger.warning(f"MCP Rate limit error in {func.__name__}: {e}")
            # Implement exponential backoff
            await asyncio.sleep(2 ** kwargs.get('retry_count', 0))
            raise
        except MCPServiceUnavailableError as e:
            logger.error(f"MCP Service unavailable in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise MCPError(f"Unexpected error: {str(e)}", details={"function": func.__name__})
    return wrapper


class MCPCircuitBreaker:
    """Circuit breaker pattern for MCP service reliability"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                self.state = "HALF_OPEN"
            else:
                raise MCPServiceUnavailableError("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            
            raise


class MCPRetryManager:
    """Manages retry logic for MCP operations"""
    
    @staticmethod
    async def retry_with_backoff(
        func,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0
    ):
        """Retry function with exponential backoff"""
        for attempt in range(max_retries + 1):
            try:
                return await func()
            except (MCPRateLimitError, MCPServiceUnavailableError) as e:
                if attempt == max_retries:
                    raise
                
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                logger.warning(f"Retry attempt {attempt + 1} after {delay}s delay: {e}")
                await asyncio.sleep(delay)
            except MCPAuthenticationError:
                # Don't retry auth errors
                raise


class SupabaseMCPIntegration:
    """Supabase MCP integration wrapper"""
    
    def __init__(self, project_ref: str, access_token: str):
        self.project_ref = project_ref
        self.access_token = access_token
        self.circuit_breaker = MCPCircuitBreaker()
    
    @mcp_error_handler
    async def get_project_url(self) -> str:
        """Get Supabase project URL via MCP"""
        # This would be implemented using actual MCP calls
        # For now, simulate the integration
        return f"https://{self.project_ref}.supabase.co"
    
    @mcp_error_handler
    async def execute_sql(self, query: str) -> Dict[str, Any]:
        """Execute SQL query via MCP"""
        # Implement actual MCP call to mcp__supabase__execute_sql
        return await self.circuit_breaker.call(self._execute_sql_internal, query)
    
    async def _execute_sql_internal(self, query: str) -> Dict[str, Any]:
        """Internal SQL execution method"""
        # This would use the actual MCP tool
        # mcp__supabase__execute_sql({"query": query})
        logger.info(f"Executing SQL via MCP: {query[:100]}...")
        return {"status": "success", "rows": []}
    
    @mcp_error_handler
    async def list_tables(self, schemas: List[str] = None) -> List[Dict[str, Any]]:
        """List tables via MCP"""
        if schemas is None:
            schemas = ["public"]
        
        # mcp__supabase__list_tables({"schemas": schemas})
        return await self.circuit_breaker.call(self._list_tables_internal, schemas)
    
    async def _list_tables_internal(self, schemas: List[str]) -> List[Dict[str, Any]]:
        """Internal table listing method"""
        logger.info(f"Listing tables for schemas: {schemas}")
        return []
    
    @mcp_error_handler
    async def apply_migration(self, name: str, query: str) -> Dict[str, Any]:
        """Apply database migration via MCP"""
        return await self.circuit_breaker.call(
            self._apply_migration_internal, 
            name, 
            query
        )
    
    async def _apply_migration_internal(self, name: str, query: str) -> Dict[str, Any]:
        """Internal migration method"""
        # mcp__supabase__apply_migration({"name": name, "query": query})
        logger.info(f"Applying migration '{name}' via MCP")
        return {"status": "success", "migration_id": name}


class RailwayMCPIntegration:
    """Railway MCP integration wrapper"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.circuit_breaker = MCPCircuitBreaker()
    
    @mcp_error_handler
    async def list_projects(self) -> List[Dict[str, Any]]:
        """List Railway projects via MCP"""
        return await self.circuit_breaker.call(self._list_projects_internal)
    
    async def _list_projects_internal(self) -> List[Dict[str, Any]]:
        """Internal projects listing method"""
        # mcp__railway__project_list()
        logger.info("Listing Railway projects via MCP")
        return []
    
    @mcp_error_handler
    async def get_project_info(self, project_id: str) -> Dict[str, Any]:
        """Get Railway project info via MCP"""
        return await self.circuit_breaker.call(
            self._get_project_info_internal, 
            project_id
        )
    
    async def _get_project_info_internal(self, project_id: str) -> Dict[str, Any]:
        """Internal project info method"""
        # mcp__railway__project_info({"projectId": project_id})
        logger.info(f"Getting Railway project info for {project_id} via MCP")
        return {"id": project_id, "name": "velro-backend"}
    
    @mcp_error_handler
    async def list_services(self, project_id: str) -> List[Dict[str, Any]]:
        """List services in Railway project via MCP"""
        return await self.circuit_breaker.call(
            self._list_services_internal, 
            project_id
        )
    
    async def _list_services_internal(self, project_id: str) -> List[Dict[str, Any]]:
        """Internal services listing method"""
        # mcp__railway__service_list({"projectId": project_id})
        logger.info(f"Listing services for project {project_id} via MCP")
        return []
    
    @mcp_error_handler
    async def deploy_service(self, project_id: str, service_id: str, environment_id: str) -> Dict[str, Any]:
        """Deploy service via MCP"""
        return await self.circuit_breaker.call(
            self._deploy_service_internal,
            project_id,
            service_id, 
            environment_id
        )
    
    async def _deploy_service_internal(self, project_id: str, service_id: str, environment_id: str) -> Dict[str, Any]:
        """Internal service deployment method"""
        # mcp__railway__deployment_trigger({
        #     "projectId": project_id,
        #     "serviceId": service_id,  
        #     "environmentId": environment_id
        # })
        logger.info(f"Deploying service {service_id} in project {project_id} via MCP")
        return {"deployment_id": "dep_123", "status": "pending"}


class ClaudeFlowMCPIntegration:
    """Claude Flow MCP integration wrapper"""
    
    def __init__(self):
        self.circuit_breaker = MCPCircuitBreaker()
    
    @mcp_error_handler
    async def init_swarm(self, topology: str = "hierarchical", max_agents: int = 8) -> Dict[str, Any]:
        """Initialize Claude Flow swarm via MCP"""
        return await self.circuit_breaker.call(
            self._init_swarm_internal,
            topology,
            max_agents
        )
    
    async def _init_swarm_internal(self, topology: str, max_agents: int) -> Dict[str, Any]:
        """Internal swarm initialization method"""
        # mcp__claude-flow__swarm_init({
        #     "topology": topology,
        #     "maxAgents": max_agents,
        #     "strategy": "balanced"
        # })
        logger.info(f"Initializing Claude Flow swarm with {topology} topology via MCP")
        return {"swarm_id": "swarm_123", "topology": topology, "max_agents": max_agents}
    
    @mcp_error_handler
    async def spawn_agent(self, agent_type: str, name: str = None, capabilities: List[str] = None) -> Dict[str, Any]:
        """Spawn Claude Flow agent via MCP"""
        return await self.circuit_breaker.call(
            self._spawn_agent_internal,
            agent_type,
            name,
            capabilities or []
        )
    
    async def _spawn_agent_internal(self, agent_type: str, name: str, capabilities: List[str]) -> Dict[str, Any]:
        """Internal agent spawning method"""
        # mcp__claude-flow__agent_spawn({
        #     "type": agent_type,
        #     "name": name,
        #     "capabilities": capabilities
        # })
        logger.info(f"Spawning Claude Flow agent '{name}' of type '{agent_type}' via MCP")
        return {"agent_id": "agent_123", "type": agent_type, "name": name}
    
    @mcp_error_handler
    async def orchestrate_task(self, task: str, strategy: str = "adaptive") -> Dict[str, Any]:
        """Orchestrate task via MCP"""
        return await self.circuit_breaker.call(
            self._orchestrate_task_internal,
            task,
            strategy
        )
    
    async def _orchestrate_task_internal(self, task: str, strategy: str) -> Dict[str, Any]:
        """Internal task orchestration method"""
        # mcp__claude-flow__task_orchestrate({
        #     "task": task,
        #     "strategy": strategy,
        #     "priority": "high"
        # })
        logger.info(f"Orchestrating task '{task}' with strategy '{strategy}' via MCP")
        return {"task_id": "task_123", "status": "pending", "strategy": strategy}


class MCPService:
    """Central MCP service coordinator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.supabase = None
        self.railway = None
        self.claude_flow = None
        self._initialize_integrations()
    
    def _initialize_integrations(self):
        """Initialize all MCP integrations"""
        # Supabase integration
        if 'supabase' in self.config:
            supabase_config = self.config['supabase']
            self.supabase = SupabaseMCPIntegration(
                project_ref=supabase_config.get('project_ref'),
                access_token=supabase_config.get('access_token')
            )
        
        # Railway integration
        if 'railway' in self.config:
            railway_config = self.config['railway']
            self.railway = RailwayMCPIntegration(
                api_token=railway_config.get('api_token')
            )
        
        # Claude Flow integration
        self.claude_flow = ClaudeFlowMCPIntegration()
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager for MCP transaction handling"""
        transaction_id = f"tx_{datetime.now().timestamp()}"
        logger.info(f"Starting MCP transaction {transaction_id}")
        
        try:
            yield transaction_id
            logger.info(f"MCP transaction {transaction_id} completed successfully")
        except Exception as e:
            logger.error(f"MCP transaction {transaction_id} failed: {e}")
            # Implement rollback logic if needed
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all MCP integrations"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "services": {}
        }
        
        # Check Supabase
        if self.supabase:
            try:
                await self.supabase.get_project_url()
                results["services"]["supabase"] = {"status": "healthy"}
            except Exception as e:
                results["services"]["supabase"] = {"status": "unhealthy", "error": str(e)}
        
        # Check Railway
        if self.railway:
            try:
                await self.railway.list_projects()
                results["services"]["railway"] = {"status": "healthy"}
            except Exception as e:
                results["services"]["railway"] = {"status": "unhealthy", "error": str(e)}
        
        # Check Claude Flow
        try:
            # Simple status check - would use actual MCP call
            results["services"]["claude_flow"] = {"status": "healthy"}
        except Exception as e:
            results["services"]["claude_flow"] = {"status": "unhealthy", "error": str(e)}
        
        return results
    
    async def batch_operations(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multiple MCP operations in batch"""
        results = []
        
        async with self.transaction() as tx_id:
            for i, operation in enumerate(operations):
                try:
                    service = operation.get('service')
                    method = operation.get('method')
                    params = operation.get('params', {})
                    
                    if service == 'supabase' and self.supabase:
                        result = await getattr(self.supabase, method)(**params)
                    elif service == 'railway' and self.railway:
                        result = await getattr(self.railway, method)(**params)
                    elif service == 'claude_flow' and self.claude_flow:
                        result = await getattr(self.claude_flow, method)(**params)
                    else:
                        raise MCPError(f"Unknown service or method: {service}.{method}")
                    
                    results.append({
                        "index": i,
                        "status": "success",
                        "result": result,
                        "transaction_id": tx_id
                    })
                    
                except Exception as e:
                    results.append({
                        "index": i,
                        "status": "error",
                        "error": str(e),
                        "transaction_id": tx_id
                    })
        
        return results


# Singleton instance
_mcp_service_instance = None


def get_mcp_service(config: Dict[str, Any] = None) -> MCPService:
    """Get or create MCP service singleton"""
    global _mcp_service_instance
    
    if _mcp_service_instance is None:
        if config is None:
            # Default configuration
            config = {
                "supabase": {
                    "project_ref": "dsqqtiturujlfldyeshp",
                    "access_token": "sbp_7d15a547bb4297b42a93091e37831bc07bfc8863"
                },
                "railway": {
                    "api_token": "b89e3ee0-0669-42d1-a040-d3e1a645bf94"
                }
            }
        
        _mcp_service_instance = MCPService(config)
    
    return _mcp_service_instance


# Utility functions for common MCP operations
async def execute_supabase_query(query: str) -> Dict[str, Any]:
    """Execute Supabase query via MCP"""
    mcp_service = get_mcp_service()
    if not mcp_service.supabase:
        raise MCPError("Supabase integration not configured")
    
    return await mcp_service.supabase.execute_sql(query)


async def deploy_railway_service(project_id: str, service_id: str, environment_id: str) -> Dict[str, Any]:
    """Deploy Railway service via MCP"""
    mcp_service = get_mcp_service()
    if not mcp_service.railway:
        raise MCPError("Railway integration not configured")
    
    return await mcp_service.railway.deploy_service(project_id, service_id, environment_id)


async def coordinate_with_claude_flow(task: str, agents: List[str] = None) -> Dict[str, Any]:
    """Coordinate task with Claude Flow via MCP"""
    mcp_service = get_mcp_service()
    
    # Initialize swarm
    swarm_result = await mcp_service.claude_flow.init_swarm()
    
    # Spawn required agents
    if agents:
        for agent_type in agents:
            await mcp_service.claude_flow.spawn_agent(agent_type)
    
    # Orchestrate task
    task_result = await mcp_service.claude_flow.orchestrate_task(task)
    
    return {
        "swarm": swarm_result,
        "task": task_result
    }