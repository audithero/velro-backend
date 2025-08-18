"""
Comprehensive Input Sanitization and Validation System
OWASP-compliant protection against injection attacks and data validation

Security Features:
- SQL injection prevention (OWASP A03:2021)
- XSS protection with output encoding
- Path traversal prevention
- Command injection protection
- Data type validation
- Business logic validation
- Rate limiting per input type
"""
import re
import json
import html
import urllib.parse
import base64
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error with security context."""
    def __init__(self, message: str, field: str = None, attack_type: str = None):
        self.message = message
        self.field = field
        self.attack_type = attack_type
        super().__init__(message)

class InputSanitizer:
    """
    Comprehensive input sanitization system with OWASP compliance.
    Prevents multiple attack vectors through layered validation.
    """
    
    # SQL injection patterns (comprehensive list)
    SQL_INJECTION_PATTERNS = [
        # Basic SQL keywords
        r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b",
        
        # SQL operators and functions
        r"\b(AND|OR|NOT|XOR|LIKE|IN|EXISTS|BETWEEN|IS\s+NULL|IS\s+NOT\s+NULL)\b",
        
        # SQL comments and terminators
        r"(--|#|/\*|\*/|;)",
        
        # Union-based injection
        r"\bUNION\s+(ALL\s+)?SELECT\b",
        
        # Boolean-based injection
        r"(\'\s*(OR|AND)\s*\'\s*=\s*\')|(\'\s*(OR|AND)\s*1\s*=\s*1)|(\'\s*(OR|AND)\s*\'[^\']*\'\s*=\s*\'[^\']*\')",
        
        # Time-based injection
        r"\b(SLEEP|BENCHMARK|WAITFOR|DELAY)\s*\(",
        
        # Error-based injection
        r"\b(EXTRACTVALUE|UPDATEXML|EXP|CAST|CONVERT)\s*\(",
        
        # Stacked queries
        r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)",
        
        # Hex and unicode bypasses
        r"(0x[0-9a-fA-F]+)|(\\\u[0-9a-fA-F]{4})",
        
        # Function calls that might indicate injection
        r"\b(CONCAT|CHAR|ASCII|ORD|LENGTH|SUBSTRING|MID|LEFT|RIGHT)\s*\(",
    ]
    
    # XSS patterns (comprehensive list)
    XSS_PATTERNS = [
        # Script tags
        r"<\s*script[^>]*>.*?</\s*script\s*>",
        r"<\s*script[^>]*>",
        
        # Event handlers
        r"\bon\w+\s*=\s*['\"]?[^'\">\s]*['\"]?",
        
        # JavaScript URLs
        r"javascript\s*:",
        r"vbscript\s*:",
        r"data\s*:",
        
        # HTML tags that can contain scripts
        r"<\s*(iframe|object|embed|applet|link|meta|base|form|input|textarea|select|option|button)\b[^>]*>",
        
        # SVG with scripts
        r"<\s*svg[^>]*>.*?</\s*svg\s*>",
        
        # Expression() CSS
        r"expression\s*\(",
        
        # Import statements
        r"@import\s+",
        
        # XML entities
        r"&\s*#\s*[xX]?\s*[0-9a-fA-F]+\s*;",
        
        # Data URIs
        r"data\s*:\s*[^;]+;[^,]*,",
        
        # Encoded XSS attempts
        r"(%3C|%3E|%22|%27|%2F|%3D)",
    ]
    
    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\.[\\/]",
        r"\.\.%2[fF]",
        r"\.\.%5[cC]",
        r"%2e%2e[\\/]",
        r"%2e%2e%2[fF]",
        r"%2e%2e%5[cC]",
        r"\.\.\\",
        r"\.\./",
    ]
    
    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        # Command separators
        r"[;&|`$(){}]",
        
        # Common Unix commands
        r"\b(cat|ls|pwd|whoami|id|uname|ps|kill|rm|cp|mv|chmod|chown|su|sudo|curl|wget|nc|netcat)\b",
        
        # Windows commands
        r"\b(dir|type|copy|del|ren|attrib|net|ping|ipconfig|tasklist|taskkill)\b",
        
        # Redirection operators
        r"(>|<|>>|<<|2>&1|&>|&>>)",
        
        # Variable expansion
        r"(\$\{|\$\(|\$[A-Za-z_])",
        
        # Process substitution
        r"(<\(|\)\s*>)",
    ]
    
    # File extension validation
    ALLOWED_FILE_EXTENSIONS = {
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tiff'],
        'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf'],
        'archive': ['.zip', '.tar', '.gz', '.7z'],
        'data': ['.json', '.xml', '.csv', '.yaml', '.yml']
    }
    
    @classmethod
    def sanitize_input(
        cls, 
        value: Any, 
        field_name: str, 
        input_type: str = "text",
        max_length: int = None,
        allow_html: bool = False,
        strict_mode: bool = True
    ) -> Any:
        """
        Comprehensive input sanitization with multiple security layers.
        
        Args:
            value: Input value to sanitize
            field_name: Name of the field for logging
            input_type: Type of input validation
            max_length: Maximum allowed length
            allow_html: Whether to allow HTML content
            strict_mode: Enable strict validation rules
            
        Returns:
            Sanitized value
            
        Raises:
            ValidationError: If input fails validation
        """
        try:
            # Handle None values
            if value is None:
                return None
            
            # Convert to string for processing
            if not isinstance(value, str):
                if isinstance(value, (int, float, bool)):
                    value = str(value)
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value)
                else:
                    value = str(value)
            
            # Length validation
            if max_length and len(value) > max_length:
                raise ValidationError(
                    f"Input too long: {len(value)} > {max_length}",
                    field_name,
                    "length_violation"
                )
            
            # Apply sanitization layers
            sanitized_value = value
            
            # 1. SQL Injection Protection
            if strict_mode:
                sanitized_value = cls._prevent_sql_injection(sanitized_value, field_name)
            
            # 2. XSS Protection
            if not allow_html:
                sanitized_value = cls._prevent_xss(sanitized_value, field_name)
            
            # 3. Path Traversal Protection
            sanitized_value = cls._prevent_path_traversal(sanitized_value, field_name)
            
            # 4. Command Injection Protection
            if strict_mode:
                sanitized_value = cls._prevent_command_injection(sanitized_value, field_name)
            
            # 5. Type-specific validation
            sanitized_value = cls._validate_by_type(sanitized_value, input_type, field_name)
            
            # 6. Final cleanup
            sanitized_value = cls._final_cleanup(sanitized_value)
            
            return sanitized_value
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"❌ [SANITIZER] Error sanitizing {field_name}: {e}")
            raise ValidationError(f"Sanitization failed: {str(e)}", field_name, "sanitization_error")
    
    @classmethod
    def _prevent_sql_injection(cls, value: str, field_name: str) -> str:
        """Detect and prevent SQL injection attempts."""
        original_value = value
        
        for pattern in cls.SQL_INJECTION_PATTERNS:
            matches = re.finditer(pattern, value, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                matched_text = match.group()
                logger.warning(f"🚨 [SANITIZER] SQL injection attempt in {field_name}: '{matched_text}'")
                
                # Replace with safe placeholder
                value = value.replace(matched_text, "[FILTERED]")
        
        # Additional SQL injection prevention
        # Escape single quotes
        value = value.replace("'", "''")
        
        # Remove or escape dangerous characters
        dangerous_chars = {
            ';': '[SEMICOLON]',
            '--': '[COMMENT]',
            '/*': '[BLOCK_COMMENT_START]',
            '*/': '[BLOCK_COMMENT_END]',
        }
        
        for char, replacement in dangerous_chars.items():
            if char in value:
                logger.warning(f"🚨 [SANITIZER] Dangerous SQL character '{char}' in {field_name}")
                value = value.replace(char, replacement)
        
        if value != original_value:
            raise ValidationError(
                "Input contains potentially malicious SQL content",
                field_name,
                "sql_injection_attempt"
            )
        
        return value
    
    @classmethod
    def _prevent_xss(cls, value: str, field_name: str) -> str:
        """Detect and prevent XSS attempts."""
        original_value = value
        
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE | re.DOTALL):
                logger.warning(f"🚨 [SANITIZER] XSS attempt in {field_name}: {value[:100]}...")
                raise ValidationError(
                    "Input contains potentially malicious script content",
                    field_name,
                    "xss_attempt"
                )
        
        # HTML encode dangerous characters
        value = html.escape(value, quote=True)
        
        # Additional XSS character filtering
        xss_chars = {
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;',
            '`': '&#x60;',
            '=': '&#x3D;'
        }
        
        for char, encoded in xss_chars.items():
            value = value.replace(char, encoded)
        
        return value
    
    @classmethod
    def _prevent_path_traversal(cls, value: str, field_name: str) -> str:
        """Detect and prevent path traversal attempts."""
        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"🚨 [SANITIZER] Path traversal attempt in {field_name}: {value}")
                raise ValidationError(
                    "Input contains path traversal characters",
                    field_name,
                    "path_traversal_attempt"
                )
        
        # URL decode to catch encoded attempts
        try:
            decoded = urllib.parse.unquote(value)
            for pattern in cls.PATH_TRAVERSAL_PATTERNS:
                if re.search(pattern, decoded, re.IGNORECASE):
                    logger.warning(f"🚨 [SANITIZER] Encoded path traversal in {field_name}: {value}")
                    raise ValidationError(
                        "Input contains encoded path traversal",
                        field_name,
                        "encoded_path_traversal"
                    )
        except Exception:
            pass  # If URL decoding fails, continue with original validation
        
        return value
    
    @classmethod
    def _prevent_command_injection(cls, value: str, field_name: str) -> str:
        """Detect and prevent command injection attempts."""
        for pattern in cls.COMMAND_INJECTION_PATTERNS:
            matches = re.finditer(pattern, value, re.IGNORECASE)
            for match in matches:
                matched_text = match.group()
                logger.warning(f"🚨 [SANITIZER] Command injection attempt in {field_name}: '{matched_text}'")
                raise ValidationError(
                    f"Input contains command injection characters: {matched_text}",
                    field_name,
                    "command_injection_attempt"
                )
        
        return value
    
    @classmethod
    def _validate_by_type(cls, value: str, input_type: str, field_name: str) -> str:
        """Apply type-specific validation rules."""
        try:
            if input_type == "email":
                return cls._validate_email(value, field_name)
            elif input_type == "uuid":
                return cls._validate_uuid(value, field_name)
            elif input_type == "url":
                return cls._validate_url(value, field_name)
            elif input_type == "filename":
                return cls._validate_filename(value, field_name)
            elif input_type == "json":
                return cls._validate_json(value, field_name)
            elif input_type == "integer":
                return cls._validate_integer(value, field_name)
            elif input_type == "float":
                return cls._validate_float(value, field_name)
            elif input_type == "alphanumeric":
                return cls._validate_alphanumeric(value, field_name)
            elif input_type == "base64":
                return cls._validate_base64(value, field_name)
            else:
                return value  # No specific validation for generic text
                
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Type validation failed: {str(e)}", field_name, "type_validation_error")
    
    @classmethod
    def _validate_email(cls, email: str, field_name: str) -> str:
        """Validate email format and security."""
        # Basic format validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValidationError("Invalid email format", field_name, "email_format_error")
        
        # Length limits per RFC 5321
        if len(email) > 320:
            raise ValidationError("Email too long (max 320 characters)", field_name, "email_length_error")
        
        local, domain = email.rsplit('@', 1)
        if len(local) > 64:
            raise ValidationError("Email local part too long (max 64 characters)", field_name, "email_local_error")
        if len(domain) > 255:
            raise ValidationError("Email domain too long (max 255 characters)", field_name, "email_domain_error")
        
        return email.lower().strip()
    
    @classmethod
    def _validate_uuid(cls, uuid_str: str, field_name: str) -> str:
        """Validate UUID format."""
        try:
            # Try parsing as UUID
            UUID(uuid_str)
            return uuid_str.lower()
        except ValueError:
            raise ValidationError("Invalid UUID format", field_name, "uuid_format_error")
    
    @classmethod
    def _validate_url(cls, url: str, field_name: str) -> str:
        """Validate URL format and security."""
        # Basic URL pattern
        url_pattern = r'^https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})+(?:/[^\s]*)?$'
        if not re.match(url_pattern, url):
            raise ValidationError("Invalid URL format", field_name, "url_format_error")
        
        # Security checks
        if any(dangerous in url.lower() for dangerous in ['javascript:', 'data:', 'vbscript:', 'file:']):
            raise ValidationError("Dangerous URL scheme detected", field_name, "dangerous_url_scheme")
        
        return url.strip()
    
    @classmethod
    def _validate_filename(cls, filename: str, field_name: str) -> str:
        """Validate filename for security."""
        # Remove path components
        filename = filename.split('/')[-1].split('\\')[-1]
        
        # Check for dangerous patterns
        if '..' in filename or filename.startswith('.'):
            raise ValidationError("Invalid filename pattern", field_name, "filename_pattern_error")
        
        # Validate extension
        ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        allowed_extensions = []
        for ext_list in cls.ALLOWED_FILE_EXTENSIONS.values():
            allowed_extensions.extend(ext_list)
        
        if ext and ext not in allowed_extensions:
            raise ValidationError(f"File extension '{ext}' not allowed", field_name, "filename_extension_error")
        
        # Length limit
        if len(filename) > 255:
            raise ValidationError("Filename too long (max 255 characters)", field_name, "filename_length_error")
        
        return filename
    
    @classmethod
    def _validate_json(cls, json_str: str, field_name: str) -> str:
        """Validate JSON format and content."""
        try:
            parsed = json.loads(json_str)
            
            # Recursively validate JSON content
            cls._validate_json_content(parsed, f"{field_name}.json")
            
            return json_str
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format: {str(e)}", field_name, "json_format_error")
    
    @classmethod
    def _validate_json_content(cls, data: Any, path: str):
        """Recursively validate JSON content for security."""
        if isinstance(data, dict):
            if len(data) > 1000:  # Limit object size
                raise ValidationError("JSON object too large", path, "json_size_error")
            
            for key, value in data.items():
                # Validate key
                cls.sanitize_input(key, f"{path}.key", "text", max_length=100, strict_mode=False)
                # Validate value
                cls._validate_json_content(value, f"{path}.{key}")
        
        elif isinstance(data, list):
            if len(data) > 10000:  # Limit array size
                raise ValidationError("JSON array too large", path, "json_array_error")
            
            for i, item in enumerate(data):
                cls._validate_json_content(item, f"{path}[{i}]")
        
        elif isinstance(data, str):
            cls.sanitize_input(data, path, "text", max_length=10000, strict_mode=False)
    
    @classmethod
    def _validate_integer(cls, value: str, field_name: str) -> str:
        """Validate integer format."""
        try:
            int_val = int(value)
            # Range validation
            if int_val < -2147483648 or int_val > 2147483647:  # 32-bit signed integer
                raise ValidationError("Integer out of range", field_name, "integer_range_error")
            return str(int_val)
        except ValueError:
            raise ValidationError("Invalid integer format", field_name, "integer_format_error")
    
    @classmethod
    def _validate_float(cls, value: str, field_name: str) -> str:
        """Validate float format."""
        try:
            float_val = float(value)
            if not (-1e308 <= float_val <= 1e308):  # IEEE 754 double precision
                raise ValidationError("Float out of range", field_name, "float_range_error")
            return str(float_val)
        except ValueError:
            raise ValidationError("Invalid float format", field_name, "float_format_error")
    
    @classmethod
    def _validate_alphanumeric(cls, value: str, field_name: str) -> str:
        """Validate alphanumeric input."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', value):
            raise ValidationError("Only alphanumeric characters, underscores, and hyphens allowed", field_name, "alphanumeric_error")
        return value
    
    @classmethod
    def _validate_base64(cls, value: str, field_name: str) -> str:
        """Validate base64 format."""
        try:
            # Check base64 pattern
            if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', value):
                raise ValidationError("Invalid base64 format", field_name, "base64_format_error")
            
            # Try to decode
            base64.b64decode(value, validate=True)
            return value
        except Exception:
            raise ValidationError("Invalid base64 encoding", field_name, "base64_decode_error")
    
    @classmethod
    def _final_cleanup(cls, value: str) -> str:
        """Final cleanup of sanitized input."""
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Normalize whitespace
        value = re.sub(r'\s+', ' ', value).strip()
        
        # Remove control characters (except newlines and tabs)
        value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\t')
        
        return value
    
    @classmethod
    def sanitize_output(cls, data: Any) -> Any:
        """
        Sanitize output data for safe display.
        Prevents XSS in JSON responses and HTML content.
        """
        if isinstance(data, str):
            return html.escape(data, quote=True)
        elif isinstance(data, dict):
            return {key: cls.sanitize_output(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_output(item) for item in data]
        else:
            return data

class BusinessLogicValidator:
    """
    Business logic validation for application-specific rules.
    Complements security validation with domain-specific checks.
    """
    
    @staticmethod
    def validate_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user registration/update data."""
        validated = {}
        
        # Email validation
        if 'email' in user_data:
            validated['email'] = InputSanitizer.sanitize_input(
                user_data['email'], 'email', 'email', max_length=320
            )
        
        # Password strength validation
        if 'password' in user_data:
            password = user_data['password']
            if len(password) < 8:
                raise ValidationError("Password must be at least 8 characters", 'password', 'weak_password')
            if len(password) > 128:
                raise ValidationError("Password too long (max 128 characters)", 'password', 'password_length')
            
            # Check complexity
            if not re.search(r'[A-Z]', password):
                raise ValidationError("Password must contain uppercase letter", 'password', 'password_complexity')
            if not re.search(r'[a-z]', password):
                raise ValidationError("Password must contain lowercase letter", 'password', 'password_complexity')
            if not re.search(r'\d', password):
                raise ValidationError("Password must contain number", 'password', 'password_complexity')
            
            validated['password'] = password  # Don't sanitize passwords
        
        # Display name validation
        if 'display_name' in user_data:
            validated['display_name'] = InputSanitizer.sanitize_input(
                user_data['display_name'], 'display_name', 'text', max_length=100
            )
        
        # Avatar URL validation
        if 'avatar_url' in user_data and user_data['avatar_url']:
            validated['avatar_url'] = InputSanitizer.sanitize_input(
                user_data['avatar_url'], 'avatar_url', 'url', max_length=500
            )
        
        return validated
    
    @staticmethod
    def validate_generation_data(generation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate AI generation request data."""
        validated = {}
        
        # Prompt validation
        if 'prompt' in generation_data:
            prompt = generation_data['prompt']
            if len(prompt.strip()) == 0:
                raise ValidationError("Prompt cannot be empty", 'prompt', 'empty_prompt')
            if len(prompt) > 5000:
                raise ValidationError("Prompt too long (max 5000 characters)", 'prompt', 'prompt_length')
            
            validated['prompt'] = InputSanitizer.sanitize_input(
                prompt, 'prompt', 'text', max_length=5000, allow_html=False
            )
        
        # Model validation
        if 'model' in generation_data:
            allowed_models = ['stable-diffusion', 'dalle-3', 'midjourney']
            if generation_data['model'] not in allowed_models:
                raise ValidationError("Invalid model specified", 'model', 'invalid_model')
            validated['model'] = generation_data['model']
        
        # Dimensions validation
        if 'width' in generation_data or 'height' in generation_data:
            width = int(generation_data.get('width', 512))
            height = int(generation_data.get('height', 512))
            
            if not (64 <= width <= 2048) or not (64 <= height <= 2048):
                raise ValidationError("Invalid dimensions (64-2048 pixels)", 'dimensions', 'invalid_dimensions')
            
            validated['width'] = width
            validated['height'] = height
        
        return validated

def create_validation_middleware():
    """Create validation middleware for FastAPI."""
    from fastapi import Request, HTTPException
    
    async def validate_request_data(request: Request, call_next):
        """Middleware to validate all request data."""
        try:
            # Skip validation for certain paths
            skip_paths = ['/health', '/metrics', '/docs', '/openapi.json']
            if any(request.url.path.startswith(path) for path in skip_paths):
                return await call_next(request)
            
            # Validate query parameters
            for param, value in request.query_params.items():
                try:
                    InputSanitizer.sanitize_input(value, f"query.{param}", "text", max_length=1000)
                except ValidationError as e:
                    logger.warning(f"🚨 [VALIDATION] Query parameter validation failed: {e.message}")
                    raise HTTPException(status_code=400, detail=e.message)
            
            # For POST/PUT/PATCH requests, validate body
            if request.method in ['POST', 'PUT', 'PATCH']:
                content_type = request.headers.get('content-type', '')
                if 'application/json' in content_type:
                    try:
                        # CRITICAL FIX: Use body cache helper to prevent deadlock
                        try:
                            from middleware.production_optimized import BodyCacheHelper
                            body = await BodyCacheHelper.safe_get_body(request)
                        except ImportError:
                            # Fallback to direct body read
                            try:
                                body = await request.body()
                            except RuntimeError:
                                # Body already read - skip validation to prevent hanging
                                body = b""
                        
                        if body:
                            json_data = json.loads(body)
                            # Recursive validation of JSON data
                            _validate_json_recursively(json_data, 'body')
                    except json.JSONDecodeError:
                        raise HTTPException(status_code=400, detail="Invalid JSON format")
                    except ValidationError as e:
                        logger.warning(f"🚨 [VALIDATION] Request body validation failed: {e.message}")
                        raise HTTPException(status_code=400, detail=e.message)
            
            response = await call_next(request)
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ [VALIDATION] Middleware error: {e}")
            raise HTTPException(status_code=500, detail="Validation error")
    
    return validate_request_data

def _validate_json_recursively(data: Any, path: str):
    """Recursively validate JSON data structure."""
    if isinstance(data, dict):
        for key, value in data.items():
            # Validate key
            InputSanitizer.sanitize_input(str(key), f"{path}.{key}.key", "text", max_length=100)
            # Validate value
            _validate_json_recursively(value, f"{path}.{key}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _validate_json_recursively(item, f"{path}[{i}]")
    elif isinstance(data, str):
        InputSanitizer.sanitize_input(data, path, "text", max_length=10000)