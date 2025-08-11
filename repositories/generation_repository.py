"""
Generation repository for database operations.
Following CLAUDE.md: Pure database layer, no business logic.
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
import logging

from database import SupabaseClient
from models.generation import GenerationResponse, GenerationStatus

logger = logging.getLogger(__name__)


class GenerationRepository:
    """Repository for generation database operations."""
    
    def __init__(self, db_client: SupabaseClient):
        self.db = db_client
    
    def _transform_db_record(self, db_record: Dict[str, Any]) -> Dict[str, Any]:
        """Transform database record to match GenerationResponse model."""
        # Create a copy to avoid mutating the original - db_record is already a dict
        transformed = db_record.copy()
        
        # Map database fields to model expected fields
        if 'generation_type' in transformed and 'media_type' not in transformed:
            transformed['media_type'] = transformed['generation_type']
        
        if 'credits_used' in transformed and 'cost' not in transformed:
            transformed['cost'] = transformed.get('credits_used', 0)
        
        if 'output_urls' in transformed and 'media_url' not in transformed:
            output_urls = transformed.get('output_urls', [])
            transformed['media_url'] = output_urls[0] if output_urls else None
        
        # Ensure required fields have defaults for NULL database values
        if 'media_type' not in transformed or transformed['media_type'] is None:
            transformed['media_type'] = 'image'  # Default type
            
        if 'cost' not in transformed or transformed['cost'] is None:
            transformed['cost'] = 0
            
        if 'prompt' not in transformed or transformed['prompt'] is None:
            transformed['prompt'] = 'Generated content'  # Default prompt for legacy records
        
        return transformed
    
    async def create_generation(self, generation_data: Dict[str, Any], auth_token: Optional[str] = None) -> GenerationResponse:
        """Create a new generation record."""
        logger.info(f"➕ [DB-CREATE] Creating new generation record in database")
        logger.info(f"🔍 [DB-CREATE] Generation data: user_id={generation_data.get('user_id')}, model_id={generation_data.get('model_id')}, status={generation_data.get('status')}")
        logger.info(f"🔍 [DB-CREATE] Generation data keys: {list(generation_data.keys())}")
        
        try:
            logger.info(f"🔍 [DB-CREATE] Executing database insert query...")
            # CRITICAL FIX: Multi-layer generation creation with auth token context
            result = None
            last_error = None
            
            # LAYER 1: Try service key first if valid
            try:
                result = self.db.execute_query(
                    "generations",
                    "insert",
                    data=generation_data,
                    user_id=generation_data.get("user_id"),
                    use_service_key=True  # Try service key first
                )
                logger.info(f"✅ [DB-CREATE] Service key insert successful")
                
            except Exception as service_error:
                logger.warning(f"⚠️ [DB-CREATE] Service key failed: {service_error}")
                last_error = service_error
                
                # LAYER 2: Fallback to anon client with auth token
                if auth_token:
                    logger.info(f"🔓 [DB-CREATE] Falling back to anon client with auth token")
                    try:
                        result = self.db.execute_query(
                            "generations",
                            "insert",
                            data=generation_data,
                            user_id=generation_data.get("user_id"),
                            auth_token=auth_token,
                            use_service_key=False
                        )
                        logger.info(f"✅ [DB-CREATE] Anon + JWT insert successful")
                        last_error = None
                        
                    except Exception as anon_error:
                        logger.error(f"❌ [DB-CREATE] Anon + JWT failed: {anon_error}")
                        last_error = anon_error
                else:
                    logger.warning(f"⚠️ [DB-CREATE] No auth token available for fallback")
            
            if not result:
                if last_error:
                    logger.error(f"❌ [DB-CREATE] All creation methods failed: {last_error}")
                    raise last_error
                else:
                    raise ValueError("Generation creation returned no data")
            
            logger.info(f"✅ [DB-CREATE] Database insert completed")
            logger.info(f"🔍 [DB-CREATE] Insert result type: {type(result)}, length: {len(result) if isinstance(result, list) else 'N/A'}")
            
            # Supabase returns a list for inserts, take the first item
            if isinstance(result, list) and len(result) > 0:
                generation_record = result[0]
                logger.info(f"🔍 [DB-CREATE] Created generation record from DB: ID={generation_record.get('id')}, Status={generation_record.get('status')}")
                transformed_record = self._transform_db_record(generation_record)
                generation_response = GenerationResponse(**transformed_record)
                logger.info(f"✅ [DB-CREATE] Generation created successfully: {generation_response.id}")
                return generation_response
            elif isinstance(result, list):
                # Empty list case
                logger.error(f"❌ [DB-CREATE] No generation record returned from database (empty list)")
                raise ValueError("No generation record returned from database")
            else:
                # Single record case (should be rare for inserts, but handle it)
                logger.info(f"🔍 [DB-CREATE] Single record result: {result}")
                transformed_record = self._transform_db_record(result)
                generation_response = GenerationResponse(**transformed_record)
                logger.info(f"✅ [DB-CREATE] Generation created successfully: {generation_response.id}")
                return generation_response
        except Exception as e:
            logger.error(f"❌ [DB-CREATE] Failed to create generation: {e}")
            logger.error(f"❌ [DB-CREATE] Create error type: {type(e).__name__}")
            logger.error(f"❌ [DB-CREATE] Failed generation data: {generation_data}")
            import traceback
            logger.error(f"❌ [DB-CREATE] Create error traceback: {traceback.format_exc()}")
            raise
    
    async def get_generation_by_id(self, generation_id: str, user_id: Optional[str] = None, auth_token: Optional[str] = None) -> Optional[GenerationResponse]:
        """Get a generation by ID with proper authentication context."""
        logger.info(f"🔍 [DB-GET] Getting generation {generation_id}, user_id={user_id}, auth_token: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        try:
            filters = {"id": generation_id}
            
            # CRITICAL FIX: Add user context to filters for RLS compliance when user_id provided
            if user_id:
                filters["user_id"] = str(user_id)  # Ensure user_id is string for JSON serialization
                logger.info(f"🔍 [DB-GET] Added user_id filter for RLS compliance: {user_id}")
            
            # CRITICAL FIX: Try service key first, then fallback to auth token (same pattern as list_user_generations)
            result = None
            try:
                # Try service key first for reliable access
                result = self.db.execute_query(
                    "generations",
                    "select",
                    filters=filters,
                    use_service_key=True,  # Use service key to bypass RLS for reliable queries
                    user_id=user_id
                )
                logger.info(f"✅ [DB-GET] Service key query successful")
            except Exception as service_error:
                logger.warning(f"⚠️ [DB-GET] Service key failed, trying auth token: {service_error}")
                # Fallback to auth token
                if auth_token:
                    result = self.db.execute_query(
                        "generations",
                        "select",
                        filters=filters,
                        auth_token=auth_token,  # Pass JWT token for RLS authentication
                        user_id=user_id  # Pass user_id for RLS context
                    )
                    logger.info(f"✅ [DB-GET] Auth token query successful")
                else:
                    logger.error(f"❌ [DB-GET] No auth token available for fallback")
                    raise service_error
            
            if result:
                logger.info(f"✅ [DB-GET] Found generation {generation_id}")
                transformed_record = self._transform_db_record(result[0])
                return GenerationResponse(**transformed_record)
            else:
                logger.warning(f"⚠️ [DB-GET] Generation {generation_id} not found or access denied")
                return None
        except Exception as e:
            logger.error(f"❌ [DB-GET] Failed to get generation {generation_id}: {e}")
            logger.error(f"❌ [DB-GET] Error type: {type(e).__name__}")
            raise
    
    async def update_generation(
        self, 
        generation_id: str, 
        update_data: Dict[str, Any]
    ) -> GenerationResponse:
        """Update a generation record."""
        logger.info(f"📝 [DB-UPDATE] Updating generation {generation_id} in database")
        logger.info(f"🔍 [DB-UPDATE] Update data keys: {list(update_data.keys())}")
        
        try:
            # Add updated_at timestamp as ISO string for JSON serialization
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Log specific important updates
            if "status" in update_data:
                logger.info(f"🔄 [DB-UPDATE] Status update: {update_data['status']}")
            if "media_url" in update_data:
                logger.info(f"🖼️ [DB-UPDATE] Media URL update: {update_data['media_url']}")
            if "output_urls" in update_data:
                logger.info(f"🔗 [DB-UPDATE] Output URLs count: {len(update_data['output_urls'])}")
            if "storage_size" in update_data:
                logger.info(f"📊 [DB-UPDATE] Storage size: {update_data['storage_size']} bytes")
            
            logger.info(f"🔍 [DB-UPDATE] Executing database update query...")
            result = self.db.execute_query(
                "generations",
                "update",
                filters={"id": str(generation_id)},  # Convert UUID to string for JSON serialization
                data=update_data,
                use_service_key=True,  # Use service key to bypass RLS for backend operations
                single=True  # Return single record instead of list
            )
            
            logger.info(f"✅ [DB-UPDATE] Database update completed successfully")
            logger.info(f"🔍 [DB-UPDATE] Raw database result keys: {list(result.keys()) if isinstance(result, dict) else 'Non-dict result'}")
            
            transformed_record = self._transform_db_record(result)
            generation_response = GenerationResponse(**transformed_record)
            
            logger.info(f"✅ [DB-UPDATE] Generation {generation_id} updated successfully")
            logger.info(f"🔍 [DB-UPDATE] Final generation status: {generation_response.status}, media_url: {generation_response.media_url}")
            
            return generation_response
        except Exception as e:
            logger.error(f"❌ [DB-UPDATE] Failed to update generation {generation_id}: {e}")
            logger.error(f"❌ [DB-UPDATE] Update error type: {type(e).__name__}")
            logger.error(f"❌ [DB-UPDATE] Update data that failed: {update_data}")
            import traceback
            logger.error(f"❌ [DB-UPDATE] Update error traceback: {traceback.format_exc()}")
            raise
    
    async def update_generation_status(
        self, 
        generation_id: str, 
        status: str
    ) -> GenerationResponse:
        """Update generation status."""
        logger.info(f"🔄 [DB-STATUS] Updating generation {generation_id} status to: {status}")
        
        update_data = {"status": status}
        
        # Add completion timestamp if completed or failed
        if status in [GenerationStatus.COMPLETED, GenerationStatus.FAILED, GenerationStatus.CANCELLED]:
            completion_time = datetime.utcnow().isoformat()
            update_data["completed_at"] = completion_time
            logger.info(f"🕰️ [DB-STATUS] Adding completion timestamp: {completion_time}")
            
        logger.info(f"🔍 [DB-STATUS] Status update data: {update_data}")
        result = await self.update_generation(generation_id, update_data)
        logger.info(f"✅ [DB-STATUS] Status update completed for generation {generation_id}")
        
        return result
    
    async def list_user_generations(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> List[GenerationResponse]:
        """List generations for a user with optional filters."""
        logger.info(f"🔍 [DB-LIST] Listing generations for user {user_id}, project_id={project_id}, auth_token: {'***' + auth_token[-10:] if auth_token else 'None'}")
        
        try:
            filters = {"user_id": str(user_id)}  # Ensure user_id is string for JSON serialization
            
            if project_id:
                filters["project_id"] = project_id
                logger.info(f"🔍 [DB-LIST] Adding project_id filter: {project_id}")
                
            if status:
                filters["status"] = status
            
            logger.info(f"🔍 [DB-LIST] Query filters: {filters}")
            
            # CRITICAL FIX: Try service key first, then fallback to auth token
            result = None
            try:
                # Try service key first for reliable access
                result = self.db.execute_query(
                    "generations",
                    "select",
                    filters=filters,
                    use_service_key=True,  # Use service key to bypass RLS for reliable queries
                    user_id=user_id
                )
                logger.info(f"✅ [DB-LIST] Service key query successful")
            except Exception as service_error:
                logger.warning(f"⚠️ [DB-LIST] Service key failed, trying auth token: {service_error}")
                # Fallback to auth token
                result = self.db.execute_query(
                    "generations",
                    "select",
                    filters=filters,
                    auth_token=auth_token,  # Pass JWT token for RLS authentication
                    user_id=user_id  # Pass user_id for RLS context
                )
            
            logger.info(f"✅ [DB-LIST] Database query returned {len(result)} records")
            if project_id:
                # Log specific project filtering results
                project_matches = [g for g in result if g.get("project_id") == project_id]
                logger.info(f"🔍 [DB-LIST] Project filter match count: {len(project_matches)} out of {len(result)} total records")
                if len(project_matches) != len(result):
                    logger.warning(f"⚠️ [DB-LIST] Project filter discrepancy detected!")
                    # Log a few example records for debugging
                    for i, gen in enumerate(result[:3]):
                        logger.info(f"🔍 [DB-LIST] Sample record {i}: project_id={gen.get('project_id')}, expected={project_id}")
            
            # Sort by created_at desc and apply pagination
            sorted_result = sorted(result, key=lambda x: x["created_at"], reverse=True)
            paginated_result = sorted_result[offset:offset + limit]
            
            logger.info(f"✅ [DB-LIST] Returning {len(paginated_result)} paginated records (offset={offset}, limit={limit})")
            
            return [GenerationResponse(**self._transform_db_record(gen)) for gen in paginated_result]
        except Exception as e:
            logger.error(f"Failed to list generations for user {user_id}: {e}")
            raise
    
    async def list_project_generations(
        self,
        project_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[GenerationResponse]:
        """List generations for a specific project."""
        return await self.list_user_generations(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
            offset=offset
        )
    
    async def delete_generation(self, generation_id: str) -> bool:
        """Delete a generation record."""
        try:
            self.db.execute_query(
                "generations",
                "delete",
                filters={"id": generation_id},
                use_service_key=True  # Use service key to bypass RLS for backend operations
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete generation {generation_id}: {e}")
            return False
    
    async def get_user_generation_stats(self, user_id: str) -> Dict[str, Any]:
        """Get generation statistics for a user."""
        try:
            logger.info(f"🔍 [GENERATION-STATS] Getting stats for user {user_id}")
            
            result = self.db.execute_query(
                "generations",
                "select",
                filters={"user_id": str(user_id)}  # Ensure user_id is string for JSON serialization
            )
            
            logger.info(f"🔍 [GENERATION-STATS] Query returned {len(result)} generations")
            
            # Calculate stats with robust string comparisons
            total_generations = len(result)
            
            # Use string values for comparison instead of enum values for better reliability
            completed_generations = len([g for g in result if str(g.get("status", "")).lower() == "completed"])
            failed_generations = len([g for g in result if str(g.get("status", "")).lower() == "failed"])
            processing_generations = len([g for g in result if str(g.get("status", "")).lower() in ["pending", "processing"]])
            favorite_generations = len([g for g in result if g.get("is_favorite", False) is True])
            
            # Handle credits_used carefully - it might be None
            total_credits_used = 0
            for g in result:
                credits = g.get("credits_used") or g.get("cost", 0)  # Fallback to cost field
                if credits and isinstance(credits, (int, float)):
                    total_credits_used += credits
            
            logger.info(f"✅ [GENERATION-STATS] Calculated: total={total_generations}, completed={completed_generations}, failed={failed_generations}, processing={processing_generations}")
            
            # Group by generation type - handle potential None values
            type_stats = {}
            for gen in result:
                gen_type = gen.get("generation_type") or gen.get("media_type", "unknown")
                if gen_type not in type_stats:
                    type_stats[gen_type] = 0
                type_stats[gen_type] += 1
            
            # Group by model - handle potential None values
            model_stats = {}
            for gen in result:
                model_id = gen.get("model_id", "unknown")
                if model_id not in model_stats:
                    model_stats[model_id] = 0
                model_stats[model_id] += 1
            
            # Calculate success rate safely
            success_rate = 0.0
            if total_generations > 0:
                success_rate = round((completed_generations / total_generations) * 100, 2)
            
            stats_result = {
                "total_generations": total_generations,
                "completed_generations": completed_generations,
                "failed_generations": failed_generations,
                "processing_generations": processing_generations,
                "favorite_generations": favorite_generations,
                "total_credits_used": total_credits_used,
                "type_breakdown": type_stats,
                "model_breakdown": model_stats,
                "success_rate": success_rate
            }
            
            logger.info(f"✅ [GENERATION-STATS] Stats calculation successful for user {user_id}")
            return stats_result
            
        except Exception as e:
            logger.error(f"❌ [GENERATION-STATS] Failed to get generation stats for user {user_id}: {e}")
            logger.error(f"❌ [GENERATION-STATS] Error type: {type(e).__name__}")
            logger.error(f"❌ [GENERATION-STATS] Error details: {str(e)}")
            
            # Return empty stats instead of crashing
            return {
                "total_generations": 0,
                "completed_generations": 0,
                "failed_generations": 0,
                "processing_generations": 0,
                "favorite_generations": 0,
                "total_credits_used": 0,
                "type_breakdown": {},
                "model_breakdown": {},
                "success_rate": 0.0,
                "error": f"Stats calculation failed: {str(e)}"
            }
    
    async def list_recent_generations(
        self,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[GenerationResponse]:
        """List recent generations across all users (admin function)."""
        try:
            filters = {}
            if status:
                filters["status"] = status
            
            result = self.db.execute_query(
                "generations",
                "select",
                filters=filters,
                use_service_key=True  # Use service key to bypass RLS for admin operations
            )
            
            # Sort by created_at desc and limit
            sorted_result = sorted(result, key=lambda x: x["created_at"], reverse=True)
            limited_result = sorted_result[:limit]
            
            return [GenerationResponse(**self._transform_db_record(gen)) for gen in limited_result]
        except Exception as e:
            logger.error(f"Failed to list recent generations: {e}")
            raise
    
    async def get_pending_generations(self) -> List[GenerationResponse]:
        """Get all pending generations that need processing."""
        return await self.list_recent_generations(
            limit=100,
            status=GenerationStatus.PENDING
        )
    
    async def get_stale_generations(self, hours: int = 1) -> List[GenerationResponse]:
        """Get generations that have been processing for too long."""
        try:
            from datetime import timedelta
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            result = self.db.execute_query(
                "generations",
                "select",
                filters={"status": GenerationStatus.PROCESSING},
                use_service_key=True  # Use service key to bypass RLS for admin operations
            )
            
            # Filter by creation time
            stale_generations = [
                gen for gen in result 
                if datetime.fromisoformat(gen["created_at"].replace('Z', '+00:00')) < cutoff_time
            ]
            
            return [GenerationResponse(**self._transform_db_record(gen)) for gen in stale_generations]
        except Exception as e:
            logger.error(f"Failed to get stale generations: {e}")
            raise