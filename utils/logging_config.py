"""
Comprehensive logging configuration for Velro API.
Performance optimized logging with structured output and metrics collection.
"""
import logging
import logging.handlers
import json
import time
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from contextlib import contextmanager
import asyncio
from functools import wraps


class PerformanceLogger:
    """Enhanced logger with performance tracking and structured output."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.metrics = {}
        
    def setup_logging(self, level: str = "INFO", enable_file_logging: bool = True):
        """Setup comprehensive logging configuration."""
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Set level
        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.setLevel(log_level)
        
        # Create formatters
        console_formatter = self._create_console_formatter()
        file_formatter = self._create_structured_formatter()
        
        # Console handler with color coding
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation (only if enabled and not in production)
        if enable_file_logging and not os.getenv("RAILWAY_ENVIRONMENT"):
            try:
                os.makedirs("logs", exist_ok=True)
                file_handler = logging.handlers.RotatingFileHandler(
                    "logs/velro_performance.log",
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=5
                )
                file_handler.setLevel(log_level)
                file_handler.setFormatter(file_formatter)
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.warning(f"Failed to setup file logging: {e}")
        
        # Performance metrics handler
        self._setup_metrics_logging()
        
        return self.logger
    
    def _create_console_formatter(self) -> logging.Formatter:
        """Create colored console formatter."""
        
        class ColoredFormatter(logging.Formatter):
            """Formatter with color coding for different log levels."""
            
            COLORS = {
                'DEBUG': '\033[36m',     # Cyan
                'INFO': '\033[32m',      # Green
                'WARNING': '\033[33m',   # Yellow
                'ERROR': '\033[31m',     # Red
                'CRITICAL': '\033[35m',  # Magenta
            }
            RESET = '\033[0m'
            
            def format(self, record):
                color = self.COLORS.get(record.levelname, '')
                record.levelname = f"{color}{record.levelname}{self.RESET}"
                return super().format(record)
        
        return ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
    
    def _create_structured_formatter(self) -> logging.Formatter:
        """Create structured JSON formatter for file output."""
        
        class StructuredFormatter(logging.Formatter):
            """JSON formatter for structured logging."""
            
            def format(self, record):
                log_entry = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                    'module': record.module,
                    'function': record.funcName,
                    'line': record.lineno,
                }
                
                # Add extra fields if present
                if hasattr(record, 'user_id'):
                    log_entry['user_id'] = record.user_id
                if hasattr(record, 'generation_id'):
                    log_entry['generation_id'] = record.generation_id
                if hasattr(record, 'request_id'):
                    log_entry['request_id'] = record.request_id
                if hasattr(record, 'performance_metrics'):
                    log_entry['performance_metrics'] = record.performance_metrics
                
                return json.dumps(log_entry)
        
        return StructuredFormatter()
    
    def _setup_metrics_logging(self):
        """Setup performance metrics collection."""
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.slow_queries = []
    
    @contextmanager
    def performance_context(self, operation: str, **kwargs):
        """Context manager for tracking operation performance."""
        start_time = time.time()
        operation_id = f"{operation}_{int(start_time * 1000)}"
        
        try:
            self.logger.info(f"🚀 [PERF] Starting {operation}", extra={
                'operation': operation,
                'operation_id': operation_id,
                **kwargs
            })
            yield operation_id
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"❌ [PERF] {operation} failed after {duration:.3f}s: {e}", extra={
                'operation': operation,
                'operation_id': operation_id,
                'duration': duration,
                'error': str(e),
                **kwargs
            })
            raise
            
        else:
            duration = time.time() - start_time
            self.logger.info(f"✅ [PERF] {operation} completed in {duration:.3f}s", extra={
                'operation': operation,
                'operation_id': operation_id,
                'duration': duration,
                **kwargs
            })
            
            # Track slow operations
            if duration > 2.0:
                self.slow_queries.append({
                    'operation': operation,
                    'duration': duration,
                    'timestamp': datetime.utcnow().isoformat(),
                    'details': kwargs
                })
    
    def log_credit_operation(self, operation: str, user_id: str, amount: int, 
                           balance_before: int, balance_after: int, **kwargs):
        """Log credit operations with full audit trail."""
        self.logger.info(f"💳 [CREDIT] {operation}: user={user_id}, amount={amount}, balance={balance_before}→{balance_after}", extra={
            'operation_type': 'credit_operation',
            'credit_operation': operation,
            'user_id': user_id,
            'amount': amount,
            'balance_before': balance_before,
            'balance_after': balance_after,
            **kwargs
        })
    
    def log_generation_lifecycle(self, generation_id: str, status: str, 
                               user_id: str, **kwargs):
        """Log generation lifecycle events."""
        self.logger.info(f"🎨 [GENERATION] {generation_id} → {status} (user: {user_id})", extra={
            'operation_type': 'generation_lifecycle',
            'generation_id': generation_id,
            'status': status,
            'user_id': user_id,
            **kwargs
        })
    
    def log_api_request(self, method: str, path: str, user_id: Optional[str] = None, 
                       response_time: Optional[float] = None, status_code: Optional[int] = None):
        """Log API requests with performance metrics."""
        self.request_count += 1
        
        if status_code and status_code >= 400:
            self.error_count += 1
        
        self.logger.info(f"🌐 [API] {method} {path} → {status_code or 'pending'} ({response_time:.3f}s)" if response_time else f"🌐 [API] {method} {path}", extra={
            'operation_type': 'api_request',
            'method': method,
            'path': path,
            'user_id': user_id,
            'response_time': response_time,
            'status_code': status_code
        })
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary statistics."""
        uptime = time.time() - self.start_time
        
        return {
            'uptime_seconds': uptime,
            'total_requests': self.request_count,
            'error_count': self.error_count,
            'error_rate': (self.error_count / max(self.request_count, 1)) * 100,
            'requests_per_second': self.request_count / max(uptime, 1),
            'slow_operations_count': len(self.slow_queries),
            'recent_slow_operations': self.slow_queries[-5:] if self.slow_queries else []
        }


# Decorator for automatic performance logging
def log_performance(operation_name: str = None):
    """Decorator to automatically log function performance."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = PerformanceLogger(func.__module__)
            op_name = operation_name or f"{func.__name__}"
            
            with logger.performance_context(op_name):
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = PerformanceLogger(func.__module__)
            op_name = operation_name or f"{func.__name__}"
            
            with logger.performance_context(op_name):
                return func(*args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Global performance logger instance
perf_logger = PerformanceLogger("velro.performance")