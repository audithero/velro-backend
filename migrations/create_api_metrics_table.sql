-- API Metrics Table Creation Script for Kong Gateway Integration
-- Execute this script in Supabase SQL Editor to create the api_metrics table
-- Date: August 5, 2025
-- Author: Kong Integration Specialist

-- Drop existing table if it exists (for clean deployment)
DROP TABLE IF EXISTS api_metrics CASCADE;

-- Create the api_metrics table
CREATE TABLE api_metrics (
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

-- Create indexes for performance optimization
CREATE INDEX idx_api_metrics_user_id ON api_metrics(user_id);
CREATE INDEX idx_api_metrics_model_id ON api_metrics(model_id);
CREATE INDEX idx_api_metrics_request_timestamp ON api_metrics(request_timestamp DESC);
CREATE INDEX idx_api_metrics_kong_request_id ON api_metrics(kong_request_id);
CREATE INDEX idx_api_metrics_status_code ON api_metrics(status_code);
CREATE INDEX idx_api_metrics_user_timestamp ON api_metrics(user_id, request_timestamp DESC);
CREATE INDEX idx_api_metrics_model_timestamp ON api_metrics(model_id, request_timestamp DESC);

-- Composite indexes for analytics queries
CREATE INDEX idx_api_metrics_user_model_timestamp 
    ON api_metrics(user_id, model_id, request_timestamp DESC);
CREATE INDEX idx_api_metrics_status_timestamp 
    ON api_metrics(status_code, request_timestamp DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE api_metrics ENABLE ROW LEVEL SECURITY;

-- Create RLS policies

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

-- Create view for API metrics analytics
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
    model_usage_json JSON;
BEGIN
    -- Get model usage as JSON
    SELECT json_object_agg(model_id, model_count) INTO model_usage_json
    FROM (
        SELECT model_id, COUNT(*) as model_count
        FROM api_metrics 
        WHERE user_id = p_user_id 
          AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours
        GROUP BY model_id
    ) model_stats;
    
    -- Build main result
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
        'model_usage', COALESCE(model_usage_json, '{}'),
        'timestamp', NOW()
    ) INTO result
    FROM api_metrics 
    WHERE user_id = p_user_id 
      AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours;
    
    -- Return default if no data found
    RETURN COALESCE(result, json_build_object(
        'user_id', p_user_id,
        'time_period_hours', p_hours,
        'total_requests', 0,
        'successful_requests', 0,
        'failed_requests', 0,
        'success_rate', 0,
        'total_credits_used', 0,
        'average_latency_ms', 0,
        'model_usage', '{}',
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
    error_breakdown_json JSON;
BEGIN
    -- Get error breakdown as JSON
    SELECT json_object_agg(status_code::TEXT, error_count) INTO error_breakdown_json
    FROM (
        SELECT status_code, COUNT(*) as error_count
        FROM api_metrics 
        WHERE model_id = p_model_id 
          AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours
          AND status_code >= 400
        GROUP BY status_code
    ) error_stats;
    
    -- Build main result
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
        'error_breakdown', COALESCE(error_breakdown_json, '{}'),
        'timestamp', NOW()
    ) INTO result
    FROM api_metrics 
    WHERE model_id = p_model_id 
      AND request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours;
    
    -- Return default if no data found
    RETURN COALESCE(result, json_build_object(
        'model_id', p_model_id,
        'time_period_hours', p_hours,
        'total_requests', 0,
        'success_rate', 0,
        'average_latency_ms', 0,
        'median_latency_ms', 0,
        'p95_latency_ms', 0,
        'total_credits_used', 0,
        'error_breakdown', '{}',
        'timestamp', NOW()
    ));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get system-wide API metrics
CREATE OR REPLACE FUNCTION get_system_api_metrics(
    p_hours INTEGER DEFAULT 24
)
RETURNS JSON AS $$
DECLARE
    result JSON;
BEGIN
    SELECT json_build_object(
        'time_period_hours', p_hours,
        'total_requests', COUNT(*),
        'total_users', COUNT(DISTINCT user_id),
        'total_models_used', COUNT(DISTINCT model_id),
        'success_rate', COALESCE(
            COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300)::FLOAT / 
            NULLIF(COUNT(*), 0), 0
        ),
        'total_credits_used', COALESCE(SUM(credits_used), 0),
        'average_latency_ms', COALESCE(AVG(latency_ms), 0),
        'p95_latency_ms', COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0),
        'top_models', (
            SELECT json_agg(json_build_object('model_id', model_id, 'requests', requests))
            FROM (
                SELECT model_id, COUNT(*) as requests
                FROM api_metrics 
                WHERE request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours
                GROUP BY model_id
                ORDER BY requests DESC
                LIMIT 10
            ) top_models_data
        ),
        'timestamp', NOW()
    ) INTO result
    FROM api_metrics 
    WHERE request_timestamp >= NOW() - INTERVAL '1 hour' * p_hours;
    
    RETURN COALESCE(result, json_build_object(
        'time_period_hours', p_hours,
        'total_requests', 0,
        'total_users', 0,
        'total_models_used', 0,
        'success_rate', 0,
        'total_credits_used', 0,
        'average_latency_ms', 0,
        'p95_latency_ms', 0,
        'top_models', '[]',
        'timestamp', NOW()
    ));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create sample data insertion function for testing
CREATE OR REPLACE FUNCTION insert_sample_api_metrics()
RETURNS TEXT AS $$
DECLARE
    sample_user_id UUID;
    sample_generation_id UUID;
BEGIN
    -- Get a sample user ID (or create one for testing)
    SELECT id INTO sample_user_id FROM users LIMIT 1;
    
    IF sample_user_id IS NULL THEN
        RETURN 'No users found - please create a user first';
    END IF;
    
    -- Get a sample generation ID (optional)
    SELECT id INTO sample_generation_id FROM generations WHERE user_id = sample_user_id LIMIT 1;
    
    -- Insert sample API metrics
    INSERT INTO api_metrics (
        user_id, generation_id, model_id, kong_request_id,
        request_timestamp, response_timestamp, latency_ms,
        status_code, external_api_provider, credits_used,
        request_size_bytes, response_size_bytes, kong_headers
    ) VALUES 
    (
        sample_user_id, sample_generation_id, 'fal-ai/flux-pro/v1.1-ultra', 
        'kong-req-' || gen_random_uuid()::text,
        NOW() - INTERVAL '5 minutes', NOW() - INTERVAL '4 minutes 45 seconds', 15000,
        200, 'fal-ai', 50,
        1024, 2048576, 
        '{"kong_proxy_latency": "250ms", "kong_upstream_latency": "14750ms"}'::jsonb
    ),
    (
        sample_user_id, NULL, 'fal-ai/veo3',
        'kong-req-' || gen_random_uuid()::text,
        NOW() - INTERVAL '3 minutes', NOW() - INTERVAL '2 minutes 30 seconds', 30000,
        200, 'fal-ai', 500,
        2048, 15728640,
        '{"kong_proxy_latency": "300ms", "kong_upstream_latency": "29700ms"}'::jsonb
    ),
    (
        sample_user_id, NULL, 'fal-ai/kling-video',
        'kong-req-' || gen_random_uuid()::text,
        NOW() - INTERVAL '1 minute', NULL, NULL,
        503, 'fal-ai', 0,
        1536, NULL,
        '{"kong_proxy_latency": "150ms", "error": "upstream_timeout"}'::jsonb
    );
    
    RETURN 'Sample API metrics inserted successfully';
END;
$$ LANGUAGE plpgsql;

-- Add table comments for documentation
COMMENT ON TABLE api_metrics IS 'Tracks external API calls through Kong Gateway for monitoring and analytics';
COMMENT ON COLUMN api_metrics.kong_request_id IS 'Kong gateway correlation ID for request tracing';
COMMENT ON COLUMN api_metrics.kong_headers IS 'Kong-specific headers and metadata as JSONB';
COMMENT ON COLUMN api_metrics.latency_ms IS 'End-to-end request latency including Kong proxy time';
COMMENT ON COLUMN api_metrics.status_code IS 'HTTP status code returned by the external API';
COMMENT ON COLUMN api_metrics.credits_used IS 'Credits consumed for this API request';

-- Grant necessary permissions
GRANT SELECT ON api_metrics TO authenticated;
GRANT SELECT ON api_metrics_analytics TO authenticated;

-- Success message
SELECT 'API Metrics table and functions created successfully!' as status;