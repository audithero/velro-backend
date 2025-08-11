"""
Secure Query Builder - SQL Injection Prevention System
=====================================================

This module provides a secure query builder that prevents SQL injection attacks
through comprehensive input validation and parameterized query construction.

OWASP Compliance:
- A03:2021 – Injection - FIXED
- A04:2021 – Insecure Design - ADDRESSED  
- A09:2021 – Security Logging and Monitoring - IMPLEMENTED

Security Features:
1. Parameterized query construction
2. Input sanitization and validation
3. Query pattern whitelisting
4. Dynamic query prevention
5. Comprehensive audit logging
"""

import logging
import re
import json
from typing import Dict, Any, List, Optional, Union, Tuple
from enum import Enum
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class QueryOperation(Enum):
    """Allowed database operations."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class SecurityLevel(Enum):
    """Security levels for different query types."""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    PRIVILEGED = "privileged"
    ADMIN = "admin"


@dataclass
class QueryAuditEvent:
    """Audit event for database queries."""
    timestamp: datetime
    operation: QueryOperation
    table: str
    user_id: Optional[str]
    parameters: Dict[str, Any]
    query_hash: str
    security_level: SecurityLevel
    execution_time_ms: Optional[float] = None
    result_count: Optional[int] = None


class QueryValidationError(Exception):
    """Raised when query validation fails."""
    pass


class SecureQueryBuilder:
    """
    Production-grade secure query builder with SQL injection prevention.
    
    Features:
    - Parameterized query construction
    - Input validation and sanitization
    - Query pattern whitelisting
    - Audit logging
    - Performance monitoring
    """
    
    # Allowed table names (whitelist approach)
    ALLOWED_TABLES = {
        'users', 'generations', 'projects', 'file_metadata', 'credit_transactions',
        'project_collaborators', 'teams', 'team_members', 'storage_files',
        'api_metrics', 'audit_logs'
    }
    
    # Allowed column patterns for different tables
    ALLOWED_COLUMNS = {
        'users': ['id', 'email', 'display_name', 'avatar_url', 'credits_balance', 'role', 'created_at', 'updated_at'],
        'generations': ['id', 'user_id', 'project_id', 'model_id', 'prompt', 'status', 'cost', 'media_url', 
                       'created_at', 'updated_at', 'completed_at', 'parent_generation_id', 'metadata'],
        'projects': ['id', 'user_id', 'name', 'description', 'visibility', 'tags', 'created_at', 'updated_at'],
        'file_metadata': ['id', 'user_id', 'bucket_name', 'file_path', 'file_size', 'content_type', 
                         'is_thumbnail', 'metadata', 'created_at']
    }
    
    # SQL injection patterns to detect and block
    DANGEROUS_PATTERNS = [
        re.compile(r"('|(\\x27)|(\\x2D)|(\\x2d))", re.IGNORECASE),  # Quote variations
        re.compile(r"(\\x3B|\\x3b|;)", re.IGNORECASE),  # Semicolon
        re.compile(r"(\\x2D\\x2D|\\x2d\\x2d|--)", re.IGNORECASE),  # Comment markers
        re.compile(r"(union\s+select|union\s+all\s+select)", re.IGNORECASE),  # Union attacks
        re.compile(r"(exec\s*\\(|sp_executesql)", re.IGNORECASE),  # Execution commands
        re.compile(r"(insert\s+into|delete\s+from|update\s+.*\s+set)", re.IGNORECASE),  # DML in parameters
        re.compile(r"(drop\s+table|truncate\s+table|alter\s+table)", re.IGNORECASE),  # DDL attacks
        re.compile(r"(script\s*>|javascript:|vbscript:)", re.IGNORECASE),  # XSS attempts
        re.compile(r"(\\x00|\\0)", re.IGNORECASE),  # Null byte injection
    ]
    
    def __init__(self, enable_audit_logging: bool = True):
        """Initialize the secure query builder."""
        self.enable_audit_logging = enable_audit_logging
        self._query_cache = {}
        self._audit_events = []
        
        logger.info("🛡️ [QUERY-BUILDER] Secure query builder initialized")
    
    def _validate_table_name(self, table_name: str) -> str:
        """
        Validate and sanitize table name.
        
        Args:
            table_name: Table name to validate
            
        Returns:
            Validated table name
            
        Raises:
            QueryValidationError: If table name is invalid
        """
        if not isinstance(table_name, str):
            raise QueryValidationError(f"Table name must be string, got {type(table_name)}")
        
        table_name = table_name.strip().lower()
        
        if not table_name:
            raise QueryValidationError("Table name cannot be empty")
        
        # Check against whitelist
        if table_name not in self.ALLOWED_TABLES:
            raise QueryValidationError(f"Table '{table_name}' not in allowed list")
        
        # Validate format (alphanumeric and underscores only)
        if not re.match(r'^[a-z_][a-z0-9_]*$', table_name):
            raise QueryValidationError(f"Invalid table name format: {table_name}")
        
        return table_name
    
    def _validate_column_name(self, column_name: str, table_name: str) -> str:
        """
        Validate and sanitize column name.
        
        Args:
            column_name: Column name to validate
            table_name: Table the column belongs to
            
        Returns:
            Validated column name
            
        Raises:
            QueryValidationError: If column name is invalid
        """
        if not isinstance(column_name, str):
            raise QueryValidationError(f"Column name must be string, got {type(column_name)}")
        
        column_name = column_name.strip().lower()
        
        if not column_name:
            raise QueryValidationError("Column name cannot be empty")
        
        # Check against whitelist for table
        allowed_columns = self.ALLOWED_COLUMNS.get(table_name, [])
        if allowed_columns and column_name not in allowed_columns:
            raise QueryValidationError(f"Column '{column_name}' not allowed for table '{table_name}'")
        
        # Validate format
        if not re.match(r'^[a-z_][a-z0-9_]*$', column_name):
            raise QueryValidationError(f"Invalid column name format: {column_name}")
        
        return column_name
    
    def _validate_parameter_value(self, value: Any, context: str = "") -> Any:
        """
        Validate and sanitize parameter values.
        
        Args:
            value: Value to validate
            context: Context for validation
            
        Returns:
            Validated value
            
        Raises:
            QueryValidationError: If value contains dangerous patterns
        """
        if value is None:
            return None
        
        # Convert to string for pattern matching
        value_str = str(value)
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.search(value_str):
                logger.error(f"🚨 [QUERY-SECURITY] Dangerous pattern detected in {context}: {pattern.pattern}")
                raise QueryValidationError(f"Dangerous content detected in parameter: {context}")
        
        # Type-specific validation
        if isinstance(value, str):
            # Limit string length to prevent DoS
            if len(value) > 10000:
                raise QueryValidationError(f"String parameter too long: {len(value)} characters")
            
            # Remove potential null bytes
            value = value.replace('\x00', '')
            
        elif isinstance(value, (int, float)):
            # Validate numeric ranges
            if isinstance(value, int) and (value < -2147483648 or value > 2147483647):
                raise QueryValidationError(f"Integer out of safe range: {value}")
        
        elif isinstance(value, UUID):
            # UUID validation is handled elsewhere, convert to string
            value = str(value)
        
        elif isinstance(value, datetime):
            # Convert datetime to ISO format
            value = value.isoformat()
        
        elif isinstance(value, (list, dict)):
            # JSON serialize complex types and validate size
            json_str = json.dumps(value)
            if len(json_str) > 50000:  # 50KB limit
                raise QueryValidationError(f"JSON parameter too large: {len(json_str)} bytes")
            value = json_str
        
        return value
    
    def _audit_query(self, operation: QueryOperation, table: str, 
                    parameters: Dict[str, Any], query_hash: str,
                    security_level: SecurityLevel = SecurityLevel.AUTHENTICATED,
                    user_id: Optional[str] = None) -> None:
        """Log query execution for security monitoring."""
        if not self.enable_audit_logging:
            return
        
        audit_event = QueryAuditEvent(
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            table=table,
            user_id=user_id[:8] + "..." if user_id else None,
            parameters={k: str(v)[:100] + "..." if len(str(v)) > 100 else str(v) 
                       for k, v in parameters.items()},
            query_hash=query_hash,
            security_level=security_level
        )
        
        self._audit_events.append(audit_event)
        
        # Log based on operation sensitivity
        if operation == QueryOperation.DELETE:
            logger.warning(f"🗑️ [QUERY-AUDIT] {json.dumps(audit_event.__dict__, default=str)}")
        elif operation == QueryOperation.UPDATE:
            logger.info(f"✏️ [QUERY-AUDIT] {json.dumps(audit_event.__dict__, default=str)}")
        else:
            logger.debug(f"📖 [QUERY-AUDIT] {json.dumps(audit_event.__dict__, default=str)}")
    
    def select(self, table: str, columns: List[str] = None, 
              where_conditions: Dict[str, Any] = None,
              order_by: Optional[str] = None, limit: Optional[int] = None,
              user_id: Optional[str] = None) -> Tuple[str, List[Any]]:
        """
        Build a secure SELECT query.
        
        Args:
            table: Table name
            columns: Columns to select (None for all)
            where_conditions: WHERE clause conditions
            order_by: ORDER BY column
            limit: LIMIT value
            user_id: User ID for audit logging
            
        Returns:
            Tuple of (query_string, parameters)
        """
        try:
            # Validate table name
            table = self._validate_table_name(table)
            
            # Build column list
            if columns:
                validated_columns = []
                for col in columns:
                    validated_columns.append(self._validate_column_name(col, table))
                columns_str = ", ".join(validated_columns)
            else:
                columns_str = "*"
            
            # Start building query
            query_parts = [f"SELECT {columns_str} FROM {table}"]
            parameters = []
            param_counter = 1
            
            # Build WHERE clause
            if where_conditions:
                where_parts = []
                validated_conditions = {}
                
                for column, value in where_conditions.items():
                    validated_column = self._validate_column_name(column, table)
                    validated_value = self._validate_parameter_value(value, f"WHERE {column}")
                    
                    where_parts.append(f"{validated_column} = ${param_counter}")
                    parameters.append(validated_value)
                    validated_conditions[validated_column] = validated_value
                    param_counter += 1
                
                if where_parts:
                    query_parts.append("WHERE " + " AND ".join(where_parts))
            else:
                validated_conditions = {}
            
            # Add ORDER BY
            if order_by:
                validated_order_column = self._validate_column_name(order_by, table)
                query_parts.append(f"ORDER BY {validated_order_column}")
            
            # Add LIMIT
            if limit:
                if not isinstance(limit, int) or limit < 1 or limit > 1000:
                    raise QueryValidationError(f"Invalid limit value: {limit}")
                query_parts.append(f"LIMIT ${param_counter}")
                parameters.append(limit)
            
            # Final query
            query = " ".join(query_parts)
            
            # Generate query hash for audit
            import hashlib
            query_hash = hashlib.sha256((query + str(parameters)).encode()).hexdigest()[:16]
            
            # Audit the query
            self._audit_query(
                QueryOperation.SELECT, table, validated_conditions, 
                query_hash, SecurityLevel.AUTHENTICATED, user_id
            )
            
            return query, parameters
            
        except Exception as e:
            logger.error(f"❌ [QUERY-BUILDER] SELECT query validation failed: {e}")
            raise QueryValidationError(f"SELECT query validation failed: {str(e)}")
    
    def insert(self, table: str, data: Dict[str, Any], 
              user_id: Optional[str] = None) -> Tuple[str, List[Any]]:
        """
        Build a secure INSERT query.
        
        Args:
            table: Table name
            data: Data to insert
            user_id: User ID for audit logging
            
        Returns:
            Tuple of (query_string, parameters)
        """
        try:
            # Validate table name
            table = self._validate_table_name(table)
            
            if not data:
                raise QueryValidationError("INSERT data cannot be empty")
            
            # Validate columns and values
            validated_columns = []
            validated_values = []
            parameters = []
            
            for column, value in data.items():
                validated_column = self._validate_column_name(column, table)
                validated_value = self._validate_parameter_value(value, f"INSERT {column}")
                
                validated_columns.append(validated_column)
                validated_values.append(validated_value)
                parameters.append(validated_value)
            
            # Build query
            columns_str = "(" + ", ".join(validated_columns) + ")"
            placeholders = "(" + ", ".join([f"${i+1}" for i in range(len(parameters))]) + ")"
            
            query = f"INSERT INTO {table} {columns_str} VALUES {placeholders}"
            
            # Generate query hash for audit
            import hashlib
            query_hash = hashlib.sha256((query + str(parameters)).encode()).hexdigest()[:16]
            
            # Audit the query
            self._audit_query(
                QueryOperation.INSERT, table, dict(zip(validated_columns, validated_values)),
                query_hash, SecurityLevel.AUTHENTICATED, user_id
            )
            
            return query, parameters
            
        except Exception as e:
            logger.error(f"❌ [QUERY-BUILDER] INSERT query validation failed: {e}")
            raise QueryValidationError(f"INSERT query validation failed: {str(e)}")
    
    def update(self, table: str, data: Dict[str, Any], 
              where_conditions: Dict[str, Any],
              user_id: Optional[str] = None) -> Tuple[str, List[Any]]:
        """
        Build a secure UPDATE query.
        
        Args:
            table: Table name
            data: Data to update
            where_conditions: WHERE clause conditions
            user_id: User ID for audit logging
            
        Returns:
            Tuple of (query_string, parameters)
        """
        try:
            # Validate table name
            table = self._validate_table_name(table)
            
            if not data:
                raise QueryValidationError("UPDATE data cannot be empty")
            
            if not where_conditions:
                raise QueryValidationError("UPDATE requires WHERE conditions for safety")
            
            parameters = []
            param_counter = 1
            
            # Build SET clause
            set_parts = []
            for column, value in data.items():
                validated_column = self._validate_column_name(column, table)
                validated_value = self._validate_parameter_value(value, f"UPDATE {column}")
                
                set_parts.append(f"{validated_column} = ${param_counter}")
                parameters.append(validated_value)
                param_counter += 1
            
            # Build WHERE clause
            where_parts = []
            validated_conditions = {}
            for column, value in where_conditions.items():
                validated_column = self._validate_column_name(column, table)
                validated_value = self._validate_parameter_value(value, f"WHERE {column}")
                
                where_parts.append(f"{validated_column} = ${param_counter}")
                parameters.append(validated_value)
                validated_conditions[validated_column] = validated_value
                param_counter += 1
            
            # Build final query
            query = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
            
            # Generate query hash for audit
            import hashlib
            query_hash = hashlib.sha256((query + str(parameters)).encode()).hexdigest()[:16]
            
            # Audit the query
            self._audit_query(
                QueryOperation.UPDATE, table, validated_conditions,
                query_hash, SecurityLevel.AUTHENTICATED, user_id
            )
            
            return query, parameters
            
        except Exception as e:
            logger.error(f"❌ [QUERY-BUILDER] UPDATE query validation failed: {e}")
            raise QueryValidationError(f"UPDATE query validation failed: {str(e)}")
    
    def delete(self, table: str, where_conditions: Dict[str, Any],
              user_id: Optional[str] = None) -> Tuple[str, List[Any]]:
        """
        Build a secure DELETE query.
        
        Args:
            table: Table name
            where_conditions: WHERE clause conditions
            user_id: User ID for audit logging
            
        Returns:
            Tuple of (query_string, parameters)
        """
        try:
            # Validate table name
            table = self._validate_table_name(table)
            
            if not where_conditions:
                raise QueryValidationError("DELETE requires WHERE conditions for safety")
            
            # Build WHERE clause
            where_parts = []
            parameters = []
            validated_conditions = {}
            param_counter = 1
            
            for column, value in where_conditions.items():
                validated_column = self._validate_column_name(column, table)
                validated_value = self._validate_parameter_value(value, f"WHERE {column}")
                
                where_parts.append(f"{validated_column} = ${param_counter}")
                parameters.append(validated_value)
                validated_conditions[validated_column] = validated_value
                param_counter += 1
            
            # Build final query
            query = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
            
            # Generate query hash for audit
            import hashlib
            query_hash = hashlib.sha256((query + str(parameters)).encode()).hexdigest()[:16]
            
            # Audit the query with high priority logging
            self._audit_query(
                QueryOperation.DELETE, table, validated_conditions,
                query_hash, SecurityLevel.PRIVILEGED, user_id
            )
            
            return query, parameters
            
        except Exception as e:
            logger.error(f"❌ [QUERY-BUILDER] DELETE query validation failed: {e}")
            raise QueryValidationError(f"DELETE query validation failed: {str(e)}")
    
    def get_audit_events(self, limit: int = 100) -> List[QueryAuditEvent]:
        """Get recent audit events for monitoring."""
        return self._audit_events[-limit:] if limit else self._audit_events


# Global secure query builder instance
secure_query_builder = SecureQueryBuilder()