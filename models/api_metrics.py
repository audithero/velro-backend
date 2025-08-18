"""
API Metrics Model for Kong Gateway Integration
Tracks external API calls, latency, errors, and usage analytics.
Based on Kong integration requirements from PRD.MD
Date: August 5, 2025
Author: Kong Integration Specialist
"""
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class APIMetrics(BaseModel):
    """API Metrics model for tracking external API usage through Kong Gateway."""
    
    id: UUID = Field(..., description="Unique identifier for the API metrics record")
    user_id: UUID = Field(..., description="User who made the API request")
    generation_id: Optional[UUID] = Field(None, description="Associated generation ID if applicable")
    model_id: str = Field(..., description="AI model identifier (e.g., fal-ai/flux-pro/v1.1-ultra)")
    kong_request_id: Optional[str] = Field(None, description="Kong gateway request correlation ID")
    
    # Timing Information
    request_timestamp: datetime = Field(..., description="When the request was initiated")
    response_timestamp: Optional[datetime] = Field(None, description="When the response was received")
    latency_ms: Optional[int] = Field(None, description="Request latency in milliseconds")
    
    # Request/Response Details
    status_code: int = Field(..., description="HTTP status code returned")
    external_api_provider: str = Field(default="fal-ai", description="External API provider name")
    credits_used: int = Field(default=0, description="Credits consumed for this request")
    error_message: Optional[str] = Field(None, description="Error message if request failed")
    
    # Size Tracking
    request_size_bytes: Optional[int] = Field(None, description="Size of request payload in bytes")
    response_size_bytes: Optional[int] = Field(None, description="Size of response payload in bytes")
    
    # Kong-Specific Headers and Metadata
    kong_headers: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Kong gateway headers and metadata")
    
    # Audit Fields
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Record last update timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "987fcdeb-51a2-43d1-9f12-123456789abc",
                "generation_id": "456e7890-f12b-34c5-d678-901234567def",
                "model_id": "fal-ai/flux-pro/v1.1-ultra",
                "kong_request_id": "req-789abc123def456",
                "request_timestamp": "2025-08-05T12:30:00Z",
                "response_timestamp": "2025-08-05T12:30:15Z",
                "latency_ms": 15000,
                "status_code": 200,
                "external_api_provider": "fal-ai",
                "credits_used": 50,
                "error_message": None,
                "request_size_bytes": 1024,
                "response_size_bytes": 2048576,
                "kong_headers": {
                    "kong_proxy_latency": "250ms",
                    "kong_upstream_latency": "14750ms",
                    "kong_service": "fal-flux-pro-ultra"
                },
                "created_at": "2025-08-05T12:30:00Z"
            }
        }
    }


class APIMetricsCreate(BaseModel):
    """Schema for creating new API metrics records."""
    
    user_id: UUID
    generation_id: Optional[UUID] = None
    model_id: str
    kong_request_id: Optional[str] = None
    request_timestamp: datetime = Field(default_factory=datetime.utcnow)
    status_code: int
    external_api_provider: str = "fal-ai"
    credits_used: int = 0
    error_message: Optional[str] = None
    request_size_bytes: Optional[int] = None
    response_size_bytes: Optional[int] = None
    kong_headers: Optional[Dict[str, Any]] = None


class APIMetricsUpdate(BaseModel):
    """Schema for updating API metrics records."""
    
    response_timestamp: Optional[datetime] = None
    latency_ms: Optional[int] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    response_size_bytes: Optional[int] = None
    kong_headers: Optional[Dict[str, Any]] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class APIMetricsSummary(BaseModel):
    """Summary statistics for API usage metrics."""
    
    user_id: UUID
    time_period_hours: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    total_credits_used: int
    average_latency_ms: float
    most_used_model: Optional[str]
    model_usage: Dict[str, int]
    error_breakdown: Dict[str, int]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class APIMetricsResponse(BaseModel):
    """Response model for API metrics queries."""
    
    metrics: list[APIMetrics]
    total_count: int
    page: int
    page_size: int
    has_next: bool


# Supabase table schema for api_metrics
API_METRICS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_id UUID REFERENCES generations(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    kong_request_id TEXT,
    
    -- Timing information
    request_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_timestamp TIMESTAMPTZ,
    latency_ms INTEGER,
    
    -- Request/Response details
    status_code INTEGER NOT NULL,
    external_api_provider TEXT NOT NULL DEFAULT 'fal-ai',
    credits_used INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    
    -- Size tracking
    request_size_bytes INTEGER,
    response_size_bytes INTEGER,
    
    -- Kong metadata (JSONB for flexible storage)
    kong_headers JSONB DEFAULT '{}',
    
    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance optimization
CREATE INDEX IF NOT EXISTS idx_api_metrics_user_id ON api_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_api_metrics_model_id ON api_metrics(model_id);
CREATE INDEX IF NOT EXISTS idx_api_metrics_request_timestamp ON api_metrics(request_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_metrics_kong_request_id ON api_metrics(kong_request_id);
CREATE INDEX IF NOT EXISTS idx_api_metrics_status_code ON api_metrics(status_code);
CREATE INDEX IF NOT EXISTS idx_api_metrics_user_timestamp ON api_metrics(user_id, request_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_metrics_model_timestamp ON api_metrics(model_id, request_timestamp DESC);

-- Composite indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_api_metrics_user_model_timestamp 
    ON api_metrics(user_id, model_id, request_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_api_metrics_status_timestamp 
    ON api_metrics(status_code, request_timestamp DESC);

-- RLS Policy for user data isolation
ALTER TABLE api_metrics ENABLE ROW LEVEL SECURITY;

-- Users can only see their own API metrics
CREATE POLICY "Users can view own api metrics" ON api_metrics
    FOR SELECT USING (auth.uid() = user_id);

-- Service role can insert/update metrics (for Kong proxy service)
CREATE POLICY "Service can manage api metrics" ON api_metrics
    FOR ALL USING (auth.role() = 'service_role');

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_api_metrics_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for automatic timestamp updates
CREATE TRIGGER trigger_api_metrics_updated_at
    BEFORE UPDATE ON api_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_api_metrics_updated_at();

-- View for API metrics analytics
CREATE OR REPLACE VIEW api_metrics_analytics AS
SELECT 
    user_id,
    model_id,
    external_api_provider,
    DATE_TRUNC('hour', request_timestamp) as hour,
    DATE_TRUNC('day', request_timestamp) as day,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300) as successful_requests,
    COUNT(*) FILTER (WHERE status_code >= 400) as failed_requests,
    SUM(credits_used) as total_credits,
    AVG(latency_ms) as avg_latency_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as median_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency_ms,
    AVG(response_size_bytes) as avg_response_size_bytes
FROM api_metrics
GROUP BY user_id, model_id, external_api_provider, hour, day;

-- Function to get user API metrics summary
CREATE OR REPLACE FUNCTION get_user_api_metrics_summary(
    p_user_id UUID,
    p_hours INTEGER DEFAULT 24
)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'user_id', p_user_id,
        'time_period_hours', p_hours,
        'total_requests', COUNT(*),
        'successful_requests', COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300),
        'failed_requests', COUNT(*) FILTER (WHERE status_code >= 400),
        'success_rate', COALESCE(
            COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300)::FLOAT / 
            NULLIF(COUNT(*), 0), 0
        ),
        'total_credits_used', COALESCE(SUM(credits_used), 0),
        'average_latency_ms', COALESCE(AVG(latency_ms), 0),
        'model_usage', json_object_agg(model_id, model_count),
        'timestamp', NOW()
    ) INTO result
    FROM (
        SELECT 
            *,
            COUNT(*) OVER (PARTITION BY model_id) as model_count
        FROM api_metrics 
        WHERE user_id = p_user_id 
          AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours
    ) metrics;
    
    RETURN COALESCE(result, json_build_object(
        'user_id', p_user_id,
        'time_period_hours', p_hours,
        'total_requests', 0,
        'successful_requests', 0,
        'failed_requests', 0,
        'success_rate', 0,
        'total_credits_used', 0,
        'average_latency_ms', 0,
        'model_usage', json_build_object(),
        'timestamp', NOW()
    ));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get model performance metrics
CREATE OR REPLACE FUNCTION get_model_performance_metrics(
    p_model_id TEXT,
    p_hours INTEGER DEFAULT 24
)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'model_id', p_model_id,
        'time_period_hours', p_hours,
        'total_requests', COUNT(*),
        'success_rate', COALESCE(
            COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300)::FLOAT / 
            NULLIF(COUNT(*), 0), 0
        ),
        'average_latency_ms', COALESCE(AVG(latency_ms), 0),
        'median_latency_ms', COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms), 0),
        'p95_latency_ms', COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0),
        'total_credits_used', COALESCE(SUM(credits_used), 0),
        'error_breakdown', json_object_agg(
            CASE 
                WHEN status_code >= 400 THEN status_code::TEXT 
                ELSE NULL 
            END, 
            error_count
        ) FILTER (WHERE status_code >= 400),
        'timestamp', NOW()
    ) INTO result
    FROM (
        SELECT 
            *,
            COUNT(*) FILTER (WHERE status_code >= 400) OVER (PARTITION BY status_code) as error_count
        FROM api_metrics 
        WHERE model_id = p_model_id 
          AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours
    ) metrics;
    
    RETURN COALESCE(result, json_build_object(
        'model_id', p_model_id,
        'time_period_hours', p_hours,
        'total_requests', 0,
        'success_rate', 0,
        'average_latency_ms', 0,
        'error_breakdown', json_build_object(),
        'timestamp', NOW()
    ));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON TABLE api_metrics IS 'Tracks external API calls through Kong Gateway for monitoring and analytics';
COMMENT ON COLUMN api_metrics.kong_request_id IS 'Kong gateway correlation ID for request tracing';
COMMENT ON COLUMN api_metrics.kong_headers IS 'Kong-specific headers and metadata as JSONB';
COMMENT ON COLUMN api_metrics.latency_ms IS 'End-to-end request latency including Kong proxy time';
"""