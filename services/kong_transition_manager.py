"""
Kong Transition Manager for Velro AI Platform
Manages progressive rollout of Kong Gateway integration with circuit breaker patterns,
health monitoring, and automatic fallback capabilities.
Date: August 6, 2025
Author: Kong Integration Specialist
"""
import asyncio
import logging
import time
import random
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from enum import Enum
import os
import httpx

logger = logging.getLogger(__name__)


class TransitionState(Enum):
    """Kong transition states for progressive rollout."""
    DISABLED = "disabled"
    CANARY = "canary"  # 5% traffic
    PARTIAL = "partial"  # 25% traffic  
    MAJORITY = "majority"  # 75% traffic
    FULL = "full"  # 100% traffic
    FALLBACK = "fallback"  # Temporary fallback due to errors


class CircuitBreakerState(Enum):
    """Circuit breaker states for Kong health management."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Kong is failing, use fallback
    HALF_OPEN = "half_open"  # Testing Kong recovery


class KongTransitionManager:
    """Manages progressive rollout and health monitoring for Kong Gateway integration."""
    
    def __init__(self):
        # Configuration from environment
        self.initial_traffic_percentage = int(os.getenv('KONG_TRAFFIC_PERCENTAGE', '0'))
        self.health_check_interval = int(os.getenv('KONG_HEALTH_CHECK_INTERVAL', '30'))
        self.circuit_breaker_threshold = int(os.getenv('KONG_CIRCUIT_BREAKER_THRESHOLD', '5'))
        self.circuit_breaker_timeout = int(os.getenv('KONG_CIRCUIT_BREAKER_TIMEOUT', '60'))
        
        # Kong configuration
        self.kong_gateway_url = os.getenv('KONG_URL', 'https://kong-production.up.railway.app')
        self.kong_api_key = os.getenv('KONG_API_KEY', 'velro-backend-key-2025-prod')
        
        # Current state management
        self.current_state = TransitionState.DISABLED
        self.circuit_breaker_state = CircuitBreakerState.CLOSED
        self.traffic_percentage = self.initial_traffic_percentage
        
        # Health monitoring
        self.consecutive_failures = 0
        self.last_health_check = None
        self.circuit_breaker_opened_at = None
        self.kong_response_times = []
        self.kong_success_rate = 1.0
        
        # HTTP client for health checks
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        
        # Initialize transition state based on traffic percentage
        self._initialize_transition_state()
        
        logger.info(f"🚀 Kong Transition Manager initialized")
        logger.info(f"🎯 Initial state: {self.current_state.value}")
        logger.info(f"📊 Initial traffic percentage: {self.traffic_percentage}%")
        logger.info(f"🔄 Health check interval: {self.health_check_interval}s")
        logger.info(f"⚡ Circuit breaker threshold: {self.circuit_breaker_threshold}")
        
    def _initialize_transition_state(self):
        """Initialize transition state based on configured traffic percentage."""
        if self.traffic_percentage == 0:
            self.current_state = TransitionState.DISABLED
        elif self.traffic_percentage <= 5:
            self.current_state = TransitionState.CANARY
        elif self.traffic_percentage <= 25:
            self.current_state = TransitionState.PARTIAL
        elif self.traffic_percentage <= 75:
            self.current_state = TransitionState.MAJORITY
        else:
            self.current_state = TransitionState.FULL
            
    async def should_use_kong(self, user_id: Optional[UUID] = None) -> Tuple[bool, str]:
        """
        Determine if Kong should be used for this request based on:
        1. Current transition state
        2. Circuit breaker state  
        3. Progressive rollout percentage
        4. User-based routing (optional)
        
        Returns:
            Tuple of (use_kong: bool, reason: str)
        """
        # Always check circuit breaker first
        if self.circuit_breaker_state == CircuitBreakerState.OPEN:
            return False, f"circuit_breaker_open"
            
        # If Kong is disabled, never use it
        if self.current_state == TransitionState.DISABLED:
            return False, f"transition_disabled"
            
        # If in fallback mode, don't use Kong
        if self.current_state == TransitionState.FALLBACK:
            return False, f"fallback_mode"
            
        # If circuit breaker is half-open, only allow limited requests
        if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            # Allow 10% of requests through for testing
            if random.random() < 0.1:
                return True, f"circuit_breaker_testing"
            return False, f"circuit_breaker_half_open"
        
        # Progressive rollout logic based on current state
        rollout_percentage = self._get_rollout_percentage()
        
        # Use deterministic routing based on user ID if provided
        if user_id:
            # Hash user ID to get consistent routing decision
            user_hash = hash(str(user_id)) % 100
            use_kong = user_hash < rollout_percentage
        else:
            # Random routing for anonymous requests
            use_kong = random.random() < (rollout_percentage / 100.0)
            
        reason = f"rollout_{self.current_state.value}_{rollout_percentage}%"
        return use_kong, reason
        
    def _get_rollout_percentage(self) -> int:
        """Get current rollout percentage based on transition state."""
        rollout_mapping = {
            TransitionState.DISABLED: 0,
            TransitionState.CANARY: 5,
            TransitionState.PARTIAL: 25,
            TransitionState.MAJORITY: 75,
            TransitionState.FULL: 100,
            TransitionState.FALLBACK: 0
        }
        return rollout_mapping.get(self.current_state, 0)
        
    async def record_kong_request_result(
        self,
        success: bool,
        response_time_ms: int,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Record the result of a Kong request for health monitoring."""
        current_time = time.time()
        
        if success:
            # Reset consecutive failures on success
            self.consecutive_failures = 0
            
            # Record response time
            self.kong_response_times.append(response_time_ms)
            
            # Keep only last 100 response times
            if len(self.kong_response_times) > 100:
                self.kong_response_times.pop(0)
                
            # If circuit breaker was half-open, consider closing it
            if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
                logger.info("✅ Kong request successful during half-open state - closing circuit breaker")
                self.circuit_breaker_state = CircuitBreakerState.CLOSED
                self.circuit_breaker_opened_at = None
                
        else:
            # Increment consecutive failures
            self.consecutive_failures += 1
            
            logger.warning(f"⚠️ Kong request failed: {error_message} (consecutive failures: {self.consecutive_failures})")
            
            # Check if we should open circuit breaker
            if (self.consecutive_failures >= self.circuit_breaker_threshold and 
                self.circuit_breaker_state == CircuitBreakerState.CLOSED):
                
                logger.error(f"❌ Opening circuit breaker due to {self.consecutive_failures} consecutive failures")
                self.circuit_breaker_state = CircuitBreakerState.OPEN
                self.circuit_breaker_opened_at = current_time
                
                # Consider automatic rollback
                await self._consider_rollback()
                
        # Update success rate
        await self._update_success_rate()
        
    async def _update_success_rate(self):
        """Update Kong success rate based on recent requests."""
        # This would typically use a sliding window of recent requests
        # For now, use a simple calculation based on consecutive failures
        if self.consecutive_failures == 0:
            self.kong_success_rate = min(1.0, self.kong_success_rate + 0.1)
        else:
            failure_penalty = min(0.2, self.consecutive_failures * 0.05)
            self.kong_success_rate = max(0.0, self.kong_success_rate - failure_penalty)
            
    async def _consider_rollback(self):
        """Consider automatic rollback based on failure patterns."""
        # If we're in a high-traffic state and experiencing failures, rollback
        high_traffic_states = [TransitionState.MAJORITY, TransitionState.FULL]
        
        if self.current_state in high_traffic_states and self.kong_success_rate < 0.8:
            logger.warning(f"🔄 Initiating automatic rollback due to low success rate: {self.kong_success_rate:.2f}")
            await self.rollback()
            
    async def advance_rollout(self) -> Tuple[bool, str]:
        """
        Advance to the next rollout stage if conditions are met.
        
        Returns:
            Tuple of (advanced: bool, reason: str)
        """
        # Check if Kong is healthy enough to advance
        if self.circuit_breaker_state != CircuitBreakerState.CLOSED:
            return False, "circuit_breaker_not_closed"
            
        if self.kong_success_rate < 0.95:
            return False, f"success_rate_too_low_{self.kong_success_rate:.2f}"
            
        # Advance to next state
        state_progression = {
            TransitionState.DISABLED: TransitionState.CANARY,
            TransitionState.CANARY: TransitionState.PARTIAL,
            TransitionState.PARTIAL: TransitionState.MAJORITY,
            TransitionState.MAJORITY: TransitionState.FULL,
            TransitionState.FALLBACK: TransitionState.CANARY
        }
        
        next_state = state_progression.get(self.current_state)
        if not next_state:
            return False, "already_at_maximum_rollout"
            
        previous_state = self.current_state
        self.current_state = next_state
        self.traffic_percentage = self._get_rollout_percentage()
        
        logger.info(f"📈 Advanced rollout: {previous_state.value} → {next_state.value} ({self.traffic_percentage}%)")
        return True, f"advanced_to_{next_state.value}"
        
    async def rollback(self) -> Tuple[bool, str]:
        """
        Rollback to previous stage or fallback mode.
        
        Returns:
            Tuple of (rolled_back: bool, reason: str)
        """
        state_rollback = {
            TransitionState.FULL: TransitionState.MAJORITY,
            TransitionState.MAJORITY: TransitionState.PARTIAL,
            TransitionState.PARTIAL: TransitionState.CANARY,
            TransitionState.CANARY: TransitionState.DISABLED,
            TransitionState.FALLBACK: TransitionState.DISABLED
        }
        
        previous_state = self.current_state
        rollback_state = state_rollback.get(self.current_state, TransitionState.DISABLED)
        
        self.current_state = rollback_state
        self.traffic_percentage = self._get_rollout_percentage()
        
        logger.warning(f"🔄 Rolled back: {previous_state.value} → {rollback_state.value} ({self.traffic_percentage}%)")
        return True, f"rolled_back_to_{rollback_state.value}"
        
    async def emergency_stop(self) -> Dict[str, Any]:
        """Emergency stop - immediately disable Kong and fallback to direct FAL.ai."""
        previous_state = self.current_state
        self.current_state = TransitionState.FALLBACK
        self.circuit_breaker_state = CircuitBreakerState.OPEN
        self.circuit_breaker_opened_at = time.time()
        self.traffic_percentage = 0
        
        logger.error(f"🚨 EMERGENCY STOP: Kong disabled - falling back to direct FAL.ai")
        
        return {
            "action": "emergency_stop",
            "previous_state": previous_state.value,
            "current_state": self.current_state.value,
            "circuit_breaker_state": self.circuit_breaker_state.value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform Kong health check and update circuit breaker state."""
        try:
            # Test Kong health endpoint
            health_url = f"{self.kong_gateway_url}/health"
            headers = {"X-API-Key": self.kong_api_key}
            
            start_time = time.time()
            response = await self.client.get(health_url, headers=headers)
            response_time = int((time.time() - start_time) * 1000)
            
            if response.status_code == 200:
                # Kong is healthy
                health_data = {
                    "kong_status": "healthy",
                    "response_time_ms": response_time,
                    "status_code": response.status_code,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Update circuit breaker state if it was open
                if self.circuit_breaker_state == CircuitBreakerState.OPEN:
                    # Check if enough time has passed to try half-open
                    if (time.time() - self.circuit_breaker_opened_at) > self.circuit_breaker_timeout:
                        logger.info("🔄 Circuit breaker timeout reached - switching to half-open")
                        self.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                        
                await self.record_kong_request_result(True, response_time)
                
            else:
                # Kong is unhealthy
                health_data = {
                    "kong_status": "unhealthy", 
                    "response_time_ms": response_time,
                    "status_code": response.status_code,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await self.record_kong_request_result(
                    False, response_time, response.status_code, f"Health check failed: {response.status_code}"
                )
                
        except Exception as e:
            # Kong is unavailable
            health_data = {
                "kong_status": "unavailable",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.record_kong_request_result(False, 30000, None, str(e))
            
        self.last_health_check = time.time()
        return health_data
        
    async def get_transition_status(self) -> Dict[str, Any]:
        """Get current transition status and health metrics."""
        avg_response_time = (
            sum(self.kong_response_times) / len(self.kong_response_times) 
            if self.kong_response_times else 0
        )
        
        return {
            "transition_state": self.current_state.value,
            "circuit_breaker_state": self.circuit_breaker_state.value,
            "traffic_percentage": self.traffic_percentage,
            "kong_success_rate": round(self.kong_success_rate, 3),
            "consecutive_failures": self.consecutive_failures,
            "average_response_time_ms": round(avg_response_time, 1),
            "circuit_breaker_opened_at": (
                datetime.fromtimestamp(self.circuit_breaker_opened_at).isoformat() 
                if self.circuit_breaker_opened_at else None
            ),
            "last_health_check": (
                datetime.fromtimestamp(self.last_health_check).isoformat() 
                if self.last_health_check else None
            ),
            "health_check_interval": self.health_check_interval,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    async def start_health_monitoring(self):
        """Start background health monitoring task."""
        logger.info(f"🔄 Starting Kong health monitoring (interval: {self.health_check_interval}s)")
        
        while True:
            try:
                health_result = await self.perform_health_check()
                logger.debug(f"🏥 Health check result: {health_result['kong_status']}")
                
            except Exception as e:
                logger.error(f"❌ Health monitoring error: {e}")
                
            await asyncio.sleep(self.health_check_interval)
            
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()


# Global transition manager instance
kong_transition_manager = KongTransitionManager()