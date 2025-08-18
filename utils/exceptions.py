"""
Custom exceptions for the Velro application with comprehensive error handling.
Following CLAUDE.md: Type-safe error handling with clear semantics and security.
"""
import uuid
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels for monitoring and alerting."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categorization for better handling and monitoring."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    DATABASE = "database"
    EXTERNAL_SERVICE = "external_service"
    SECURITY = "security"
    SYSTEM = "system"
    BUSINESS_LOGIC = "business_logic"


class VelroError(Exception):
    """Base exception for all Velro-specific errors with enhanced context."""
    
    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        user_message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code or self._generate_error_code()
        self.severity = severity
        self.category = category
        self.user_message = user_message or message
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc)
    
    def _generate_error_code(self) -> str:
        """Generate a unique error code for tracking."""
        class_name = self.__class__.__name__
        timestamp = int(self.timestamp.timestamp() * 1000) if hasattr(self, 'timestamp') else int(datetime.now().timestamp() * 1000)
        return f"{class_name.upper()}_{timestamp}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging and API responses."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message": self.user_message,
            "severity": self.severity.value,
            "category": self.category.value,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "exception_type": self.__class__.__name__
        }


# ============================================================================
# AUTHORIZATION-SPECIFIC EXCEPTIONS
# ============================================================================

class AuthorizationError(VelroError):
    """Base class for authorization-related errors."""
    
    def __init__(
        self, 
        message: str,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        user_id: Optional[str] = None,
        required_permission: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.AUTHORIZATION)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        super().__init__(message, **kwargs)
        
        self.resource_id = resource_id
        self.resource_type = resource_type
        self.user_id = user_id
        self.required_permission = required_permission
        
        # Add authorization-specific context
        self.context.update({
            'resource_id': resource_id,
            'resource_type': resource_type,
            'user_id': user_id,
            'required_permission': required_permission
        })


class UUIDAuthorizationError(AuthorizationError):
    """Specific error for UUID-based authorization failures."""
    
    def __init__(
        self, 
        message: str,
        uuid_value: Optional[str] = None,
        uuid_type: Optional[str] = None,
        ownership_check_failed: bool = False,
        **kwargs
    ):
        # Set user-friendly message for UUID authorization failures
        user_message = kwargs.pop('user_message', None)
        if not user_message:
            if ownership_check_failed:
                user_message = "Access denied. You don't have permission to access this resource."
            else:
                user_message = "Access denied. Invalid or expired authorization."
        
        super().__init__(
            message, 
            user_message=user_message,
            error_code=f"UUID_AUTH_{int(datetime.now().timestamp() * 1000)}",
            **kwargs
        )
        
        self.uuid_value = uuid_value
        self.uuid_type = uuid_type
        self.ownership_check_failed = ownership_check_failed
        
        # Add UUID-specific context
        self.context.update({
            'uuid_value': uuid_value,
            'uuid_type': uuid_type,
            'ownership_check_failed': ownership_check_failed
        })


class GenerationAccessDeniedError(UUIDAuthorizationError):
    """Specific error for generation access denial (HTTP 403)."""
    
    def __init__(
        self, 
        generation_id: str,
        user_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        **kwargs
    ):
        message = f"Access denied to generation {generation_id}"
        user_message = "Access denied. You don't have permission to access this generation."
        
        super().__init__(
            message,
            uuid_value=generation_id,
            uuid_type="generation",
            resource_id=generation_id,
            resource_type="generation",
            user_id=user_id,
            ownership_check_failed=True,
            user_message=user_message,
            error_code=f"GEN_ACCESS_DENIED_{int(datetime.now().timestamp() * 1000)}",
            **kwargs
        )
        
        self.generation_id = generation_id
        self.owner_id = owner_id
        
        self.context.update({
            'generation_id': generation_id,
            'owner_id': owner_id,
            'access_type': 'generation_access'
        })


class ProjectAccessDeniedError(UUIDAuthorizationError):
    """Specific error for project access denial."""
    
    def __init__(
        self, 
        project_id: str,
        user_id: Optional[str] = None,
        **kwargs
    ):
        message = f"Access denied to project {project_id}"
        user_message = "Access denied. You don't have permission to access this project."
        
        super().__init__(
            message,
            uuid_value=project_id,
            uuid_type="project",
            resource_id=project_id,
            resource_type="project",
            user_id=user_id,
            ownership_check_failed=True,
            user_message=user_message,
            **kwargs
        )
        
        self.project_id = project_id


class TeamAccessDeniedError(UUIDAuthorizationError):
    """Specific error for team access denial."""
    
    def __init__(
        self, 
        team_id: str,
        user_id: Optional[str] = None,
        **kwargs
    ):
        message = f"Access denied to team {team_id}"
        user_message = "Access denied. You're not a member of this team."
        
        super().__init__(
            message,
            uuid_value=team_id,
            uuid_type="team",
            resource_id=team_id,
            resource_type="team",
            user_id=user_id,
            ownership_check_failed=True,
            user_message=user_message,
            **kwargs
        )
        
        self.team_id = team_id


# ============================================================================
# AUTHENTICATION EXCEPTIONS
# ============================================================================

class AuthenticationError(VelroError):
    """Base class for authentication-related errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.AUTHENTICATION)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('user_message', 'Authentication failed. Please log in again.')
        super().__init__(message, **kwargs)


class TokenValidationError(AuthenticationError):
    """Error for token validation failures."""
    
    def __init__(
        self, 
        message: str,
        token_type: Optional[str] = None,
        validation_failure_reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        
        self.token_type = token_type
        self.validation_failure_reason = validation_failure_reason
        
        self.context.update({
            'token_type': token_type,
            'validation_failure_reason': validation_failure_reason
        })


class SessionExpiredError(AuthenticationError):
    """Error for expired sessions."""
    
    def __init__(self, message: str = "Session has expired", **kwargs):
        kwargs.setdefault('user_message', 'Your session has expired. Please log in again.')
        super().__init__(message, **kwargs)


# ============================================================================
# OTHER EXCEPTIONS (ENHANCED)
# ============================================================================

class NotFoundError(VelroError):
    """Raised when a requested resource is not found."""
    
    def __init__(
        self, 
        message: str,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('user_message', 'The requested resource was not found.')
        super().__init__(message, **kwargs)
        
        self.resource_id = resource_id
        self.resource_type = resource_type
        
        self.context.update({
            'resource_id': resource_id,
            'resource_type': resource_type
        })


class ConflictError(VelroError):
    """Raised when there's a conflict with existing resources."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('user_message', 'This action conflicts with existing data.')
        super().__init__(message, **kwargs)


class ForbiddenError(VelroError):
    """Raised when access to a resource is forbidden."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.AUTHORIZATION)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('user_message', 'Access denied. You don\'t have permission to perform this action.')
        super().__init__(message, **kwargs)


class ValidationError(VelroError):
    """Raised when input validation fails."""
    
    def __init__(
        self, 
        message: str,
        field_errors: Optional[Dict[str, List[str]]] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.VALIDATION)
        kwargs.setdefault('user_message', 'The provided data is invalid. Please check your input.')
        super().__init__(message, **kwargs)
        
        self.field_errors = field_errors or {}
        self.context.update({'field_errors': self.field_errors})


class DatabaseError(VelroError):
    """Raised when database operations fail."""
    
    def __init__(
        self, 
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.DATABASE)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('user_message', 'A database error occurred. Please try again later.')
        super().__init__(message, **kwargs)
        
        self.operation = operation
        self.table = table
        
        self.context.update({
            'operation': operation,
            'table': table
        })


class ExternalServiceError(VelroError):
    """Raised when external service calls fail."""
    
    def __init__(
        self, 
        message: str,
        service_name: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.EXTERNAL_SERVICE)
        kwargs.setdefault('user_message', 'An external service is currently unavailable. Please try again later.')
        super().__init__(message, **kwargs)
        
        self.service_name = service_name
        self.status_code = status_code
        
        self.context.update({
            'service_name': service_name,
            'status_code': status_code
        })


class SecurityError(VelroError):
    """Raised when security violations are detected."""
    
    def __init__(
        self, 
        message: str,
        security_event_type: Optional[str] = None,
        threat_level: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.SECURITY)
        kwargs.setdefault('severity', ErrorSeverity.CRITICAL)
        kwargs.setdefault('user_message', 'A security violation was detected. This incident has been logged.')
        super().__init__(message, **kwargs)
        
        self.security_event_type = security_event_type
        self.threat_level = threat_level
        
        self.context.update({
            'security_event_type': security_event_type,
            'threat_level': threat_level
        })


class ConfigurationError(VelroError):
    """Raised when configuration is invalid."""
    
    def __init__(
        self, 
        message: str,
        config_key: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.SYSTEM)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('user_message', 'A configuration error occurred. Please contact support.')
        super().__init__(message, **kwargs)
        
        self.config_key = config_key
        self.context.update({'config_key': config_key})


# ============================================================================
# CIRCUIT BREAKER EXCEPTIONS
# ============================================================================

class CircuitBreakerError(VelroError):
    """Raised when circuit breaker is open."""
    
    def __init__(
        self, 
        message: str,
        service_name: Optional[str] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.SYSTEM)
        kwargs.setdefault('severity', ErrorSeverity.HIGH)
        kwargs.setdefault('user_message', 'Service is temporarily unavailable. Please try again later.')
        super().__init__(message, **kwargs)
        
        self.service_name = service_name
        self.context.update({'service_name': service_name})


class RateLimitError(VelroError):
    """Raised when rate limits are exceeded."""
    
    def __init__(
        self, 
        message: str,
        limit: Optional[int] = None,
        reset_time: Optional[datetime] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.SYSTEM)
        kwargs.setdefault('user_message', 'Rate limit exceeded. Please try again later.')
        super().__init__(message, **kwargs)
        
        self.limit = limit
        self.reset_time = reset_time
        
        self.context.update({
            'limit': limit,
            'reset_time': reset_time.isoformat() if reset_time else None
        })


# ============================================================================
# BUSINESS LOGIC EXCEPTIONS
# ============================================================================

class InsufficientCreditsError(VelroError):
    """Raised when user has insufficient credits."""
    
    def __init__(
        self, 
        message: str,
        required_credits: Optional[int] = None,
        available_credits: Optional[int] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.BUSINESS_LOGIC)
        kwargs.setdefault('user_message', 'Insufficient credits. Please add more credits to continue.')
        super().__init__(message, **kwargs)
        
        self.required_credits = required_credits
        self.available_credits = available_credits
        
        self.context.update({
            'required_credits': required_credits,
            'available_credits': available_credits
        })


class QuotaExceededError(VelroError):
    """Raised when usage quota is exceeded."""
    
    def __init__(
        self, 
        message: str,
        quota_type: Optional[str] = None,
        current_usage: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs
    ):
        kwargs.setdefault('category', ErrorCategory.BUSINESS_LOGIC)
        kwargs.setdefault('user_message', 'Usage quota exceeded. Please upgrade your plan or wait for the quota to reset.')
        super().__init__(message, **kwargs)
        
        self.quota_type = quota_type
        self.current_usage = current_usage
        self.limit = limit
        
        self.context.update({
            'quota_type': quota_type,
            'current_usage': current_usage,
            'limit': limit
        })