"""
Project repository for database operations.
Following CLAUDE.md: Repository layer for data access.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from supabase import Client

from models.project import ProjectCreate, ProjectUpdate, ProjectResponse


class ProjectRepository:
    """Repository for project data operations."""
    
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
    
    async def create_project(self, user_id: UUID, project_data: ProjectCreate) -> ProjectResponse:
        """Create a new project."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"🏗️ [PROJECT_REPO] Creating project for user {user_id}")
            logger.info(f"🔍 [PROJECT_REPO] Input user_id type: {type(user_id)}")
            logger.info(f"🔍 [PROJECT_REPO] Input user_id value: {user_id}")
            
            # Convert ProjectCreate to dict for Supabase
            project_dict = {
                "user_id": str(user_id),
                "name": project_data.name,  # New name field
                "title": project_data.name,  # Map to legacy title field (required)
                "description": project_data.description,
                "visibility": project_data.visibility.value,
                "tags": project_data.tags,  # Include tags array
                "metadata": project_data.metadata,  # Include metadata JSONB
                # Let database set created_at and updated_at automatically
            }
            
            logger.info(f"🔍 [PROJECT_REPO] Project dict to insert: {project_dict}")
            
            result = self.supabase.table("projects").insert(project_dict).execute()
            
            logger.info(f"🔍 [PROJECT_REPO] Supabase insert result: {result}")
            logger.info(f"🔍 [PROJECT_REPO] Result data: {result.data}")
            logger.info(f"🔍 [PROJECT_REPO] Result count: {result.count}")
            
            if not result.data:
                logger.error(f"❌ [PROJECT_REPO] No data returned from insert")
                raise ValueError("Failed to create project - no data returned")
                
            project_row = result.data[0]
            logger.info(f"✅ [PROJECT_REPO] Project row created: {project_row}")
            
            project_response = self._row_to_project_response(project_row)
            logger.info(f"✅ [PROJECT_REPO] Project response created: {project_response}")
            
            return project_response
            
        except Exception as e:
            logger.error(f"❌ [PROJECT_REPO] Database error creating project: {str(e)}")
            logger.error(f"❌ [PROJECT_REPO] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [PROJECT_REPO] Full traceback: {traceback.format_exc()}")
            raise ValueError(f"Database error creating project: {str(e)}")
    
    async def get_project(self, project_id: UUID, user_id: UUID) -> Optional[ProjectResponse]:
        """Get project by ID if user has access."""
        try:
            result = self.supabase.table("projects").select("*").eq("id", str(project_id)).execute()
            
            if not result.data:
                return None
                
            project_row = result.data[0]
            
            # Check if user has access (owner)
            if project_row["user_id"] == str(user_id):
                return self._row_to_project_response(project_row)
            
            # Check if project is public
            if project_row["visibility"] == "public":
                return self._row_to_project_response(project_row)
            
            return None
            
        except Exception as e:
            raise ValueError(f"Database error getting project: {str(e)}")
    
    async def list_user_projects(
        self, 
        user_id: UUID, 
        skip: int = 0, 
        limit: int = 50,
        visibility: Optional[str] = None
    ) -> List[ProjectResponse]:
        """List projects accessible to user."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Get user's own projects or public projects
            # Use separate queries for OR condition in Supabase Python client
            user_projects = self.supabase.table("projects").select("*").eq("user_id", str(user_id))
            public_projects = self.supabase.table("projects").select("*").eq("visibility", "public")
            
            # If visibility filter specified, apply to both queries
            if visibility:
                user_projects = user_projects.eq("visibility", visibility)
                public_projects = public_projects.eq("visibility", visibility)
            
            # Execute both queries and combine results
            user_result = user_projects.execute()
            public_result = public_projects.execute()
            
            # Combine and deduplicate results
            all_projects = {}
            for row in user_result.data:
                all_projects[row["id"]] = row
            for row in public_result.data:
                all_projects[row["id"]] = row
            
            # Sort by updated_at descending
            sorted_projects = sorted(all_projects.values(), key=lambda x: x["updated_at"], reverse=True)
            
            # Apply pagination
            paginated_projects = sorted_projects[skip:skip + limit]
            
            projects = []
            for row in paginated_projects:
                projects.append(self._row_to_project_response(row))
            
            return projects
            
        except Exception as e:
            raise ValueError(f"Database error listing projects: {str(e)}")
    
    async def update_project(
        self, 
        project_id: UUID, 
        user_id: UUID, 
        project_data: ProjectUpdate
    ) -> Optional[ProjectResponse]:
        """Update project if user has permission."""
        try:
            # First check if user has permission to update
            project = await self.get_project(project_id, user_id)
            if not project:
                return None
                
            # Check if user is owner
            current_result = self.supabase.table("projects").select("*").eq("id", str(project_id)).execute()
            if not current_result.data:
                return None
                
            current_project = current_result.data[0]
            
            # Only owner can update
            if current_project["user_id"] != str(user_id):
                return None
            
            # Build update dict
            update_dict = {"updated_at": datetime.utcnow().isoformat()}
            
            if project_data.name is not None:
                update_dict["name"] = project_data.name
                update_dict["title"] = project_data.name  # Keep title in sync
            if project_data.description is not None:
                update_dict["description"] = project_data.description
            if project_data.visibility is not None:
                update_dict["visibility"] = project_data.visibility.value
            if project_data.tags is not None:
                update_dict["tags"] = project_data.tags
            if project_data.metadata is not None:
                update_dict["metadata"] = project_data.metadata
            
            result = self.supabase.table("projects").update(update_dict).eq("id", str(project_id)).execute()
            
            if not result.data:
                raise ValueError("Failed to update project")
                
            updated_row = result.data[0]
            return self._row_to_project_response(updated_row)
            
        except Exception as e:
            raise ValueError(f"Database error updating project: {str(e)}")
    
    async def delete_project(self, project_id: UUID, user_id: UUID) -> bool:
        """Delete project if user has permission."""
        try:
            # First check if user is owner
            result = self.supabase.table("projects").select("*").eq("id", str(project_id)).eq("user_id", str(user_id)).execute()
            
            if not result.data:
                return False
            
            # Delete the project
            delete_result = self.supabase.table("projects").delete().eq("id", str(project_id)).execute()
            
            return len(delete_result.data) > 0
            
        except Exception as e:
            raise ValueError(f"Database error deleting project: {str(e)}")
    
    async def get_project_generation_count(self, project_id: UUID) -> int:
        """Get generation count for project."""
        try:
            result = self.supabase.table("generations").select("id", count="exact").eq("project_id", str(project_id)).execute()
            return result.count or 0
            
        except Exception as e:
            raise ValueError(f"Database error getting generation count: {str(e)}")
    
    def _normalize_timestamp(self, timestamp_str: str) -> datetime:
        """Normalize timestamp string to proper isoformat."""
        # Replace Z with +00:00 for timezone
        timestamp_str = timestamp_str.replace('Z', '+00:00')
        
        # Handle microseconds padding - Python expects 6 digits, but Supabase might return 1-5
        if '.' in timestamp_str and '+' in timestamp_str:
            date_part, tz_part = timestamp_str.rsplit('+', 1)
            if '.' in date_part:
                date_main, microseconds = date_part.split('.')
                # Pad microseconds to 6 digits
                microseconds = microseconds.ljust(6, '0')[:6]
                timestamp_str = f"{date_main}.{microseconds}+{tz_part}"
        
        return datetime.fromisoformat(timestamp_str)

    def _row_to_project_response(self, row: Dict[str, Any]) -> ProjectResponse:
        """Convert database row to ProjectResponse."""
        return ProjectResponse(
            id=UUID(row["id"]),
            user_id=UUID(row["user_id"]),
            name=row.get("name") or row.get("title"),  # Try name first, fallback to title
            description=row.get("description"),
            visibility=row["visibility"],
            tags=row.get("tags", []),  # Tags array from database
            metadata=row.get("metadata", {}),  # Metadata JSONB from database
            generation_count=row.get("generations_count", 0),
            created_at=self._normalize_timestamp(row["created_at"]),
            updated_at=self._normalize_timestamp(row["updated_at"])
        )