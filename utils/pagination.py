"""
Pagination utilities for database queries.
Following CLAUDE.md: Consistent pagination patterns.
Fixed for Supabase compatibility without SQLAlchemy dependency.
"""
from typing import Tuple, List, Any, TypeVar
from pydantic import BaseModel, Field

T = TypeVar('T')


class PaginationParams(BaseModel):
    """Pagination parameters for API requests."""
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")
    
    @property
    def offset(self) -> int:
        """Calculate offset from page and per_page."""
        return (self.page - 1) * self.per_page
    
    @property
    def limit(self) -> int:
        """Get limit (same as per_page)."""
        return self.per_page


class PaginationMeta(BaseModel):
    """Pagination metadata for responses."""
    page: int
    per_page: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    items: List[Any]
    meta: PaginationMeta


async def paginate_supabase_query(
    table_query,
    pagination: PaginationParams,
    count_column: str = "*"
) -> Tuple[List[Any], int]:
    """
    Paginate a Supabase query and return results with total count.
    
    Args:
        table_query: Supabase table query object
        pagination: Pagination parameters
        count_column: Column to count for total (default: *)
    
    Returns:
        Tuple of (paginated results, total count)
    """
    # Get total count first
    count_result = table_query.select(f"count({count_column})", count="exact").execute()
    total = count_result.count if hasattr(count_result, 'count') else 0
    
    # Apply pagination and get data
    paginated_result = (table_query
                       .select("*")
                       .range(pagination.offset, pagination.offset + pagination.limit - 1)
                       .execute())
    
    items = paginated_result.data if hasattr(paginated_result, 'data') else []
    
    return items, total


def create_pagination_meta(
    page: int,
    per_page: int,
    total_items: int
) -> PaginationMeta:
    """Create pagination metadata."""
    total_pages = max(1, (total_items + per_page - 1) // per_page)  # Ceiling division
    
    return PaginationMeta(
        page=page,
        per_page=per_page,
        total_items=total_items,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )