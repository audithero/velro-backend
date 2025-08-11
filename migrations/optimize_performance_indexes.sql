-- Performance Optimization Indexes
-- PRD Alignment: Section 5.4.7 - Database Optimization

-- Users table indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_auth_lookup 
    ON users(id, is_active, email) 
    WHERE is_active = true;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email_active 
    ON users(email, is_active) 
    WHERE is_active = true;

-- Generations table indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generations_auth_access 
    ON generations(id, user_id, project_id, status, created_at) 
    WHERE status = 'completed';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generations_user_project 
    ON generations(user_id, project_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_generations_parent 
    ON generations(parent_generation_id) 
    WHERE parent_generation_id IS NOT NULL;

-- Projects table indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_user_visibility 
    ON projects(user_id, visibility, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_team_access 
    ON projects(id, visibility) 
    WHERE visibility IN ('team-only', 'public');

-- Team members table indexes (if exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'team_members') THEN
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_members_auth_fast 
            ON team_members(user_id, team_id, role, is_active) 
            WHERE is_active = true;
            
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_members_team_role 
            ON team_members(team_id, role) 
            WHERE is_active = true;
    END IF;
END $$;

-- File metadata table indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_file_metadata_user_project 
    ON file_metadata(user_id, project_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_file_metadata_generation_files 
    ON file_metadata(generation_id, is_thumbnail) 
    WHERE generation_id IS NOT NULL;

-- Style stacks table indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_style_stacks_user_public 
    ON style_stacks(user_id, is_marketplace) 
    WHERE is_marketplace = true;

-- Create materialized view for user authorization context
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_user_authorization_context AS
SELECT 
    u.id as user_id,
    u.email,
    u.is_active,
    u.current_plan,
    COUNT(DISTINCT p.id) as project_count,
    COUNT(DISTINCT g.id) as generation_count,
    MAX(g.created_at) as last_generation_at,
    COALESCE(
        json_agg(DISTINCT 
            jsonb_build_object(
                'team_id', tm.team_id,
                'role', tm.role
            )
        ) FILTER (WHERE tm.team_id IS NOT NULL),
        '[]'::json
    ) as team_memberships
FROM users u
LEFT JOIN projects p ON p.user_id = u.id
LEFT JOIN generations g ON g.user_id = u.id
LEFT JOIN team_members tm ON tm.user_id = u.id AND tm.is_active = true
WHERE u.is_active = true
GROUP BY u.id, u.email, u.is_active, u.current_plan;

-- Create index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_user_auth_context_user_id 
    ON mv_user_authorization_context(user_id);

-- Refresh the materialized view
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_user_authorization_context;

-- Analyze tables for query planner
ANALYZE users;
ANALYZE projects;
ANALYZE generations;
ANALYZE file_metadata;
ANALYZE style_stacks;
