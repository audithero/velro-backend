"""
Database integration module to bridge standard database.py with optimized database_optimized.py
This allows gradual migration to the optimized client while maintaining compatibility.
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional, Union
from config import settings
from database import SupabaseClient, db as standard_db
from database_optimized import HighPerformanceSupabaseClient, get_optimized_database_client

logger = logging.getLogger(__name__)

class IntegratedDatabaseClient:
    """
    Integrated database client that uses optimized client for performance-critical operations
    and falls back to standard client for compatibility.
    """
    
    def __init__(self):
        self.standard_client = standard_db
        self.optimized_client = None
        self.use_optimized = False
        self._initialization_attempted = False
    
    async def initialize_optimized_client(self):
        """Initialize the optimized client if not already done."""
        if not self._initialization_attempted:
            self._initialization_attempted = True
            try:
                logger.info("🚀 [DB-INTEGRATION] Initializing optimized database client...")
                self.optimized_client = await get_optimized_database_client()
                self.use_optimized = True
                logger.info("✅ [DB-INTEGRATION] Optimized client initialized successfully")
                
                # Log performance targets
                stats = self.optimized_client.get_performance_stats()
                logger.info(f"📊 [DB-INTEGRATION] Performance targets - Response time: <{self.optimized_client.TARGET_RESPONSE_TIME_MS}ms, Cache hit rate: >{self.optimized_client.TARGET_CACHE_HIT_RATE:.1%}")
                
            except Exception as e:
                logger.error(f"❌ [DB-INTEGRATION] Failed to initialize optimized client: {e}")
                logger.error("⚠️ [DB-INTEGRATION] Falling back to standard database client")
                self.use_optimized = False
    
    async def execute_query(
        self,
        table: str,
        operation: str,
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        single: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        auth_token: Optional[str] = None,
        use_optimized: Optional[bool] = None
    ) -> Any:
        """
        Execute database query with automatic optimization selection.
        
        Args:
            use_optimized: Override automatic optimization selection
            ... (other args same as standard client)
        """
        # Initialize optimized client if not done yet
        await self.initialize_optimized_client()
        
        # Determine which client to use
        should_use_optimized = use_optimized if use_optimized is not None else self.use_optimized
        
        # Use optimized client for performance-critical operations
        if should_use_optimized and self.optimized_client:
            try:
                query_type = self._determine_query_type(table, operation, user_id)
                
                # Map standard client parameters to optimized client format
                result = await self.optimized_client.execute_optimized_query(
                    query_type=query_type,
                    table=table,
                    operation=operation,
                    filters=filters,
                    data=data,
                    user_id=user_id,
                    use_service_key=use_service_key,
                    cache_ttl=300,  # 5 minutes default cache
                    auth_token=auth_token
                )
                
                # Handle single result flag
                if single and result and isinstance(result, list) and len(result) > 0:
                    return result[0]
                
                return result
                
            except Exception as optimized_error:
                logger.warning(f"⚠️ [DB-INTEGRATION] Optimized query failed, falling back to standard: {optimized_error}")
                # Fall through to standard client
        
        # Use standard client as fallback or primary
        return self.standard_client.execute_query(
            table=table,
            operation=operation,
            data=data,
            filters=filters,
            user_id=user_id,
            use_service_key=use_service_key,
            single=single,
            order_by=order_by,
            limit=limit,
            offset=offset,
            auth_token=auth_token
        )
    
    async def execute_authorization_check(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        operation: str = "read"
    ) -> Dict[str, Any]:
        """
        Execute ultra-fast authorization check using optimized client when available.
        This is critical for meeting <75ms response time requirements.
        """
        # Initialize optimized client if not done yet
        await self.initialize_optimized_client()
        
        if self.use_optimized and self.optimized_client:
            try:
                return await self.optimized_client.execute_authorization_check(
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    operation=operation
                )
            except Exception as optimized_error:
                logger.warning(f"⚠️ [DB-INTEGRATION] Optimized auth check failed, using fallback: {optimized_error}")
        
        # Fallback to basic authorization check
        try:
            if resource_type == "generation":
                # Basic generation authorization using standard client
                result = self.standard_client.execute_query(
                    table="generations",
                    operation="select",
                    filters={"id": resource_id},
                    use_service_key=True,
                    single=True
                )
                
                if not result:
                    return {"access_granted": False, "reason": "generation_not_found"}
                
                # Check ownership
                if result.get("user_id") == user_id:
                    return {"access_granted": True, "reason": "owner", "role": "owner"}
                elif result.get("visibility") == "public":
                    access = True if operation == "read" else False
                    return {"access_granted": access, "reason": "public_visibility", "role": "viewer"}
                else:
                    return {"access_granted": False, "reason": "private_resource"}
            
            elif resource_type == "project":
                # Basic project authorization using standard client
                result = self.standard_client.execute_query(
                    table="projects",
                    operation="select",
                    filters={"id": resource_id},
                    use_service_key=True,
                    single=True
                )
                
                if not result:
                    return {"access_granted": False, "reason": "project_not_found"}
                
                # Check ownership
                if result.get("user_id") == user_id:
                    return {"access_granted": True, "reason": "owner", "role": "owner"}
                elif result.get("visibility") == "public":
                    access = True if operation == "read" else False
                    return {"access_granted": access, "reason": "public_visibility", "role": "viewer"}
                else:
                    return {"access_granted": False, "reason": "private_resource"}
            
            return {"access_granted": False, "reason": "unknown_resource_type"}
            
        except Exception as e:
            logger.error(f"❌ [DB-INTEGRATION] Authorization fallback failed: {e}")
            return {"access_granted": False, "reason": "authorization_error"}
    
    def _determine_query_type(self, table: str, operation: str, user_id: Optional[str] = None) -> str:
        """Determine query type for optimization."""
        if table in ["users", "user_profiles"] and operation == "select":
            return "auth"
        elif table == "credit_transactions":
            return "credit"
        elif table == "generations":
            return "generation"
        else:
            return "general"
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics from both clients."""
        stats = {
            "optimized_client_active": self.use_optimized,
            "standard_client_available": self.standard_client.is_available()
        }
        
        if self.use_optimized and self.optimized_client:
            optimized_stats = self.optimized_client.get_performance_stats()
            stats.update({
                "optimized": optimized_stats
            })
        
        return stats
    
    def is_available(self) -> bool:
        """Check if database is available."""
        return self.standard_client.is_available()
    
    @property
    def client(self):
        """Get regular client (for backward compatibility)."""
        return self.standard_client.client
    
    @property
    def service_client(self):
        """Get service client (for backward compatibility)."""
        return self.standard_client.service_client

# Global integrated database instance
integrated_db = IntegratedDatabaseClient()

async def get_integrated_database() -> IntegratedDatabaseClient:
    """Dependency injection for integrated database client."""
    return integrated_db

# Compatibility functions to maintain existing API
async def get_database():
    """Backward compatibility - returns integrated client."""
    return integrated_db

def health_check() -> bool:
    """Check database connection health."""
    return integrated_db.is_available()