-- Migration 014: L3 Cache Materialized Views and Performance Optimization
-- Creates materialized views for L3 database cache layer with sub-100ms targets
-- Implements advanced indexing and query optimization for 10,000+ concurrent users

-- Performance monitoring for cache operations
CREATE TABLE IF NOT EXISTS cache_performance_realtime (
    id SERIAL PRIMARY KEY,
    cache_level VARCHAR(20) NOT NULL CHECK (cache_level IN ('L1_MEMORY', 'L2_REDIS', 'L3_DATABASE')),
    operation_type VARCHAR(20) NOT NULL CHECK (operation_type IN ('GET', 'SET', 'DELETE', 'INVALIDATE', 'WARM')),
    cache_key_hash VARCHAR(64) NOT NULL, -- SHA256 hash for privacy
    response_time_ms DECIMAL(10,3) NOT NULL,
    hit BOOLEAN NOT NULL DEFAULT FALSE,
    cache_size_bytes INTEGER DEFAULT 0,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id UUID, -- Optional for user-specific analytics
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Partition cache performance table by date for better performance
CREATE TABLE IF NOT EXISTS cache_performance_202508 PARTITION OF cache_performance_realtime
FOR VALUES FROM ('2025-08-01') TO ('2025-09-01');

CREATE TABLE IF NOT EXISTS cache_performance_202509 PARTITION OF cache_performance_realtime  
FOR VALUES FROM ('2025-09-01') TO ('2025-10-01');

-- Index for fast cache performance queries
CREATE INDEX IF NOT EXISTS idx_cache_perf_timestamp_level 
ON cache_performance_realtime (timestamp DESC, cache_level);

CREATE INDEX IF NOT EXISTS idx_cache_perf_key_hash 
ON cache_performance_realtime (cache_key_hash);

CREATE INDEX IF NOT EXISTS idx_cache_perf_user_timestamp 
ON cache_performance_realtime (user_id, timestamp DESC) 
WHERE user_id IS NOT NULL;

-- Materialized View: User Authorization Context for L3 Cache
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_user_authorization_context AS
SELECT 
    u.id as user_id,
    u.email,
    u.is_active as user_active,
    g.id as generation_id,
    g.project_id,
    p.name as project_name,
    p.visibility as project_visibility,
    g.status as generation_status,
    
    -- Direct ownership check
    (g.user_id = u.id) as is_direct_owner,
    
    -- Team membership check
    COALESCE(tm.role, 'none') as team_role,
    COALESCE(tm.is_active, false) as is_team_member,
    
    -- Access determination
    CASE 
        WHEN g.user_id = u.id THEN TRUE
        WHEN p.visibility = 'public_read' THEN TRUE
        WHEN p.visibility = 'team_open' AND tm.is_active = true THEN TRUE
        WHEN p.visibility = 'team_only' AND tm.is_active = true AND tm.role IN ('contributor', 'editor', 'admin', 'owner') THEN TRUE
        ELSE FALSE
    END as has_read_access,
    
    -- Access method for caching
    CASE 
        WHEN g.user_id = u.id THEN 'direct_ownership'
        WHEN p.visibility = 'public_read' THEN 'public_access'
        WHEN p.visibility IN ('team_open', 'team_only') AND tm.is_active = true THEN 'team_membership'
        ELSE 'no_access'
    END as access_method,
    
    -- Effective role for permissions
    CASE 
        WHEN g.user_id = u.id THEN 'owner'
        WHEN tm.is_active = true THEN tm.role
        ELSE 'none'
    END as effective_role,
    
    -- Performance metrics
    g.created_at,
    g.updated_at,
    u.last_active_at,
    
    -- Cache invalidation tracking
    GREATEST(g.updated_at, p.updated_at, COALESCE(tm.updated_at, '1970-01-01'::timestamp)) as last_modified

FROM users u
CROSS JOIN generations g
LEFT JOIN projects p ON g.project_id = p.id
LEFT JOIN teams t ON p.team_id = t.id
LEFT JOIN team_members tm ON t.id = tm.team_id AND u.id = tm.user_id

WHERE u.is_active = true 
  AND g.status IN ('completed', 'processing', 'queued')
  AND g.created_at >= CURRENT_DATE - INTERVAL '30 days' -- Only recent generations

WITH DATA;

-- Unique index for fast authorization lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_auth_context_user_generation 
ON mv_user_authorization_context (user_id, generation_id);

-- Index for project-based queries
CREATE INDEX IF NOT EXISTS idx_mv_auth_context_project_user 
ON mv_user_authorization_context (project_id, user_id, has_read_access);

-- Index for access method filtering
CREATE INDEX IF NOT EXISTS idx_mv_auth_context_access_method 
ON mv_user_authorization_context (access_method, last_modified DESC);

-- Materialized View: Team Collaboration Patterns for Cache Warming
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_team_collaboration_patterns AS
SELECT 
    t.id as team_id,
    t.name as team_name,
    COUNT(DISTINCT tm.user_id) as active_members,
    COUNT(DISTINCT p.id) as total_projects,
    COUNT(DISTINCT g.id) as total_generations,
    
    -- Collaboration metrics
    AVG(CASE WHEN g.status = 'completed' THEN 1.0 ELSE 0.0 END) as success_rate,
    COUNT(DISTINCT g.id) FILTER (WHERE g.created_at >= CURRENT_DATE - INTERVAL '7 days') as recent_activity,
    
    -- Cache warming priority
    CASE 
        WHEN COUNT(DISTINCT g.id) FILTER (WHERE g.created_at >= CURRENT_DATE - INTERVAL '24 hours') > 10 THEN 'high'
        WHEN COUNT(DISTINCT g.id) FILTER (WHERE g.created_at >= CURRENT_DATE - INTERVAL '7 days') > 5 THEN 'medium'
        ELSE 'low'
    END as cache_warming_priority,
    
    -- Performance scoring for cache decisions
    (
        COUNT(DISTINCT tm.user_id) * 0.3 +  -- Team size
        COUNT(DISTINCT g.id) FILTER (WHERE g.created_at >= CURRENT_DATE - INTERVAL '7 days') * 0.4 +  -- Recent activity
        AVG(CASE WHEN g.status = 'completed' THEN 1.0 ELSE 0.0 END) * 100 * 0.3  -- Success rate
    ) as collaboration_score,
    
    -- Timestamps for cache invalidation
    t.created_at as team_created_at,
    MAX(g.created_at) as last_generation_at,
    MAX(tm.updated_at) as last_membership_update

FROM teams t
LEFT JOIN team_members tm ON t.id = tm.team_id AND tm.is_active = true
LEFT JOIN projects p ON t.id = p.team_id
LEFT JOIN generations g ON p.id = g.project_id AND g.created_at >= CURRENT_DATE - INTERVAL '30 days'

WHERE t.is_active = true
GROUP BY t.id, t.name, t.created_at
HAVING COUNT(DISTINCT tm.user_id) > 0  -- Only teams with active members

WITH DATA;

-- Index for cache warming queries
CREATE INDEX IF NOT EXISTS idx_mv_team_collab_priority_score 
ON mv_team_collaboration_patterns (cache_warming_priority, collaboration_score DESC);

CREATE INDEX IF NOT EXISTS idx_mv_team_collab_activity 
ON mv_team_collaboration_patterns (last_generation_at DESC, active_members DESC);

-- Materialized View: Generation Performance Stats for Analytics Cache
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_generation_performance_stats AS
SELECT 
    g.id as generation_id,
    g.user_id,
    g.project_id,
    g.status,
    g.model_name,
    
    -- Performance metrics
    EXTRACT(EPOCH FROM (g.completed_at - g.created_at)) * 1000 as generation_time_ms,
    
    -- Success metrics
    CASE WHEN g.status = 'completed' THEN 1.0 ELSE 0.0 END as success_indicator,
    
    -- Usage patterns for cache optimization
    CASE 
        WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 'hot'
        WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 'warm'
        WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN 'cool'
        ELSE 'cold'
    END as cache_temperature,
    
    -- Access frequency estimation
    COALESCE(access_stats.access_count, 0) as estimated_access_count,
    
    -- Cache priority scoring
    (
        CASE WHEN g.status = 'completed' THEN 2.0 ELSE 0.5 END * 
        LOG(1 + COALESCE(access_stats.access_count, 0)) *
        CASE 
            WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 3.0
            WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 2.0
            WHEN g.created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN 1.0
            ELSE 0.1
        END
    ) as cache_priority_score,
    
    -- File sizes for cache sizing decisions  
    COALESCE(
        (SELECT SUM(COALESCE(file_size_bytes, 1024)) 
         FROM generation_files gf 
         WHERE gf.generation_id = g.id), 
        0
    ) as total_file_size_bytes,
    
    -- Timestamps
    g.created_at,
    g.completed_at,
    g.updated_at

FROM generations g
LEFT JOIN (
    -- Estimate access frequency from cache logs (if available)
    SELECT 
        SUBSTRING(cache_key_hash FROM 1 FOR 8) as generation_key_fragment,
        COUNT(*) as access_count
    FROM cache_performance_realtime 
    WHERE timestamp >= CURRENT_DATE - INTERVAL '7 days'
      AND hit = true
    GROUP BY SUBSTRING(cache_key_hash FROM 1 FOR 8)
) access_stats ON RIGHT(g.id::text, 8) = access_stats.generation_key_fragment

WHERE g.created_at >= CURRENT_DATE - INTERVAL '30 days'

WITH DATA;

-- Index for performance-based cache decisions
CREATE INDEX IF NOT EXISTS idx_mv_gen_perf_priority_temp 
ON mv_generation_performance_stats (cache_temperature, cache_priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_mv_gen_perf_user_recent 
ON mv_generation_performance_stats (user_id, created_at DESC)
WHERE cache_temperature IN ('hot', 'warm');

-- Materialized View: Cache Performance Analytics
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_cache_performance_analytics AS
SELECT 
    cache_level,
    operation_type,
    DATE_TRUNC('hour', timestamp) as hour_bucket,
    
    -- Performance metrics
    COUNT(*) as total_operations,
    COUNT(*) FILTER (WHERE hit = true) as hits,
    COUNT(*) FILTER (WHERE hit = false) as misses,
    
    -- Hit rate calculation  
    CASE 
        WHEN COUNT(*) > 0 THEN 
            (COUNT(*) FILTER (WHERE hit = true)::decimal / COUNT(*) * 100)
        ELSE 0 
    END as hit_rate_percent,
    
    -- Response time statistics
    AVG(response_time_ms) as avg_response_time_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms) as p50_response_time_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_response_time_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms) as p99_response_time_ms,
    MIN(response_time_ms) as min_response_time_ms,
    MAX(response_time_ms) as max_response_time_ms,
    
    -- Cache sizing
    AVG(COALESCE(cache_size_bytes, 0)) as avg_cache_size_bytes,
    SUM(COALESCE(cache_size_bytes, 0)) as total_cache_size_bytes,
    
    -- Performance targets compliance
    COUNT(*) FILTER (WHERE 
        (cache_level = 'L1_MEMORY' AND response_time_ms <= 5.0) OR
        (cache_level = 'L2_REDIS' AND response_time_ms <= 20.0) OR  
        (cache_level = 'L3_DATABASE' AND response_time_ms <= 100.0)
    ) as operations_meeting_target,
    
    -- Target compliance rate
    CASE 
        WHEN COUNT(*) > 0 THEN 
            (COUNT(*) FILTER (WHERE 
                (cache_level = 'L1_MEMORY' AND response_time_ms <= 5.0) OR
                (cache_level = 'L2_REDIS' AND response_time_ms <= 20.0) OR  
                (cache_level = 'L3_DATABASE' AND response_time_ms <= 100.0)
            )::decimal / COUNT(*) * 100)
        ELSE 0 
    END as target_compliance_percent

FROM cache_performance_realtime
WHERE timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY cache_level, operation_type, DATE_TRUNC('hour', timestamp)

WITH DATA;

-- Index for cache analytics queries
CREATE INDEX IF NOT EXISTS idx_mv_cache_analytics_level_hour 
ON mv_cache_performance_analytics (cache_level, hour_bucket DESC);

CREATE INDEX IF NOT EXISTS idx_mv_cache_analytics_hit_rate 
ON mv_cache_performance_analytics (hit_rate_percent DESC, hour_bucket DESC);

-- Redis cache configuration table
CREATE TABLE IF NOT EXISTS redis_cache_config (
    id SERIAL PRIMARY KEY,
    cache_name VARCHAR(100) NOT NULL UNIQUE,
    redis_host VARCHAR(255) NOT NULL DEFAULT 'localhost',
    redis_port INTEGER NOT NULL DEFAULT 6379,
    redis_db INTEGER NOT NULL DEFAULT 0,
    max_connections INTEGER NOT NULL DEFAULT 20,
    connection_timeout_ms INTEGER NOT NULL DEFAULT 5000,
    read_timeout_ms INTEGER NOT NULL DEFAULT 3000,
    enabled BOOLEAN NOT NULL DEFAULT true,
    priority INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Default Redis cache configurations
INSERT INTO redis_cache_config (cache_name, redis_host, redis_port, redis_db, max_connections, priority) 
VALUES 
    ('authorization_cache', 'localhost', 6379, 0, 25, 1),
    ('session_cache', 'localhost', 6379, 1, 20, 2),
    ('generation_cache', 'localhost', 6379, 2, 15, 3),
    ('team_cache', 'localhost', 6379, 3, 10, 4)
ON CONFLICT (cache_name) DO NOTHING;

-- Cache warming patterns configuration
CREATE TABLE IF NOT EXISTS cache_warming_patterns (
    id SERIAL PRIMARY KEY,
    cache_name VARCHAR(100) NOT NULL REFERENCES redis_cache_config(cache_name),
    pattern_name VARCHAR(100) NOT NULL,
    key_pattern VARCHAR(255) NOT NULL, -- Pattern like 'perm:*', 'team:*'
    warm_batch_size INTEGER NOT NULL DEFAULT 100,
    priority INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_warmed TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Default cache warming patterns
INSERT INTO cache_warming_patterns (cache_name, pattern_name, key_pattern, warm_batch_size, priority)
VALUES 
    ('authorization_cache', 'Recent Permissions', 'perm:*', 500, 1),
    ('authorization_cache', 'Active Users', 'user:*', 200, 2),
    ('team_cache', 'Team Memberships', 'team:*', 100, 3),
    ('generation_cache', 'Recent Generations', 'gen:*', 300, 4)
ON CONFLICT DO NOTHING;

-- Performance monitoring function for cache operations
CREATE OR REPLACE FUNCTION record_cache_performance(
    p_cache_level VARCHAR,
    p_operation_type VARCHAR,
    p_cache_key VARCHAR,
    p_response_time_ms DECIMAL,
    p_hit BOOLEAN DEFAULT false,
    p_cache_size_bytes INTEGER DEFAULT 0,
    p_user_id UUID DEFAULT NULL,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS VOID AS $$
DECLARE
    key_hash VARCHAR(64);
BEGIN
    -- Hash the cache key for privacy
    key_hash := encode(digest(p_cache_key, 'sha256'), 'hex');
    
    -- Insert performance record
    INSERT INTO cache_performance_realtime (
        cache_level,
        operation_type, 
        cache_key_hash,
        response_time_ms,
        hit,
        cache_size_bytes,
        user_id,
        metadata
    ) VALUES (
        p_cache_level,
        p_operation_type,
        key_hash,
        p_response_time_ms,
        p_hit,
        p_cache_size_bytes,
        p_user_id,
        p_metadata
    );
END;
$$ LANGUAGE plpgsql;

-- Function to refresh all cache-related materialized views
CREATE OR REPLACE FUNCTION refresh_cache_materialized_views() RETURNS TABLE(view_name TEXT, success BOOLEAN, refresh_time_ms DECIMAL) AS $$
DECLARE
    start_time TIMESTAMP;
    end_time TIMESTAMP;
    views_to_refresh TEXT[] := ARRAY[
        'mv_user_authorization_context',
        'mv_team_collaboration_patterns', 
        'mv_generation_performance_stats',
        'mv_cache_performance_analytics'
    ];
    view_name TEXT;
BEGIN
    FOREACH view_name IN ARRAY views_to_refresh
    LOOP
        BEGIN
            start_time := clock_timestamp();
            
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', view_name);
            
            end_time := clock_timestamp();
            
            RETURN QUERY SELECT 
                view_name::TEXT,
                true::BOOLEAN,
                EXTRACT(EPOCH FROM (end_time - start_time)) * 1000;
                
        EXCEPTION WHEN OTHERS THEN
            end_time := clock_timestamp();
            
            RETURN QUERY SELECT 
                view_name::TEXT,
                false::BOOLEAN,
                EXTRACT(EPOCH FROM (end_time - start_time)) * 1000;
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Automatic materialized view refresh job (to be scheduled)
CREATE OR REPLACE FUNCTION schedule_cache_view_refresh() RETURNS VOID AS $$
BEGIN
    -- This function would be called by a scheduler like pg_cron
    -- Refresh views every 15 minutes during business hours
    -- Every hour during off-hours
    
    IF EXTRACT(hour FROM CURRENT_TIME) BETWEEN 8 AND 18 THEN
        -- Business hours: refresh every 15 minutes  
        PERFORM refresh_cache_materialized_views();
    ELSE
        -- Off hours: refresh every hour
        IF EXTRACT(minute FROM CURRENT_TIME) = 0 THEN
            PERFORM refresh_cache_materialized_views();
        END IF;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Cache cleanup function for old performance data
CREATE OR REPLACE FUNCTION cleanup_old_cache_performance_data(days_to_keep INTEGER DEFAULT 7) RETURNS INTEGER AS $$
DECLARE
    rows_deleted INTEGER;
BEGIN
    DELETE FROM cache_performance_realtime 
    WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '1 day' * days_to_keep;
    
    GET DIAGNOSTICS rows_deleted = ROW_COUNT;
    
    RETURN rows_deleted;
END;
$$ LANGUAGE plpgsql;

-- Indexes for enhanced query performance on main tables
-- These indexes support the materialized views and cache operations

-- Enhanced generations table indexes for cache queries
CREATE INDEX IF NOT EXISTS idx_generations_cache_hot_path 
ON generations (status, created_at DESC, user_id, project_id) 
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';

CREATE INDEX IF NOT EXISTS idx_generations_completion_time 
ON generations (completed_at DESC, created_at) 
WHERE status = 'completed' AND completed_at IS NOT NULL;

-- Enhanced team_members indexes for authorization cache
CREATE INDEX IF NOT EXISTS idx_team_members_cache_lookup 
ON team_members (user_id, team_id, role, is_active, updated_at);

-- Enhanced projects indexes for visibility checks
CREATE INDEX IF NOT EXISTS idx_projects_visibility_cache 
ON projects (visibility, team_id, updated_at);

-- Enhanced users indexes for cache warming
CREATE INDEX IF NOT EXISTS idx_users_active_cache_warming 
ON users (is_active, last_active_at DESC) 
WHERE is_active = true;

-- Grant permissions for cache performance monitoring
GRANT SELECT, INSERT ON cache_performance_realtime TO velro_backend;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO velro_backend;
GRANT SELECT ON mv_user_authorization_context TO velro_backend;
GRANT SELECT ON mv_team_collaboration_patterns TO velro_backend;
GRANT SELECT ON mv_generation_performance_stats TO velro_backend;
GRANT SELECT ON mv_cache_performance_analytics TO velro_backend;
GRANT SELECT, INSERT, UPDATE, DELETE ON redis_cache_config TO velro_backend;
GRANT SELECT, INSERT, UPDATE, DELETE ON cache_warming_patterns TO velro_backend;

-- Update sequences
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO velro_backend;

COMMENT ON TABLE cache_performance_realtime IS 'Real-time cache performance monitoring for L1/L2/L3 optimization';
COMMENT ON MATERIALIZED VIEW mv_user_authorization_context IS 'Pre-computed authorization context for sub-100ms cache lookups';
COMMENT ON MATERIALIZED VIEW mv_team_collaboration_patterns IS 'Team collaboration patterns for intelligent cache warming';
COMMENT ON MATERIALIZED VIEW mv_generation_performance_stats IS 'Generation performance statistics for cache optimization';
COMMENT ON MATERIALIZED VIEW mv_cache_performance_analytics IS 'Cache performance analytics for monitoring and optimization';

-- Migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 014 completed: L3 Cache Materialized Views and Performance Optimization';
    RAISE NOTICE 'Created materialized views: mv_user_authorization_context, mv_team_collaboration_patterns, mv_generation_performance_stats, mv_cache_performance_analytics';
    RAISE NOTICE 'Created performance monitoring: cache_performance_realtime table with partitioning';
    RAISE NOTICE 'Created Redis configuration: redis_cache_config and cache_warming_patterns tables';
    RAISE NOTICE 'Performance target: Sub-100ms authorization times with >90% hit rate';
END $$;