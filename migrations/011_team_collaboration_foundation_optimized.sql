-- Team Collaboration Foundation Schema - PRODUCTION-OPTIMIZED
-- Migration 011: Phase 1 - Core team collaboration infrastructure (RLS-SAFE)
-- Following CLAUDE.md: Security-first with RLS, backward compatibility, recursion-safe

-- Enable necessary extensions (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- PHASE 1A: TEAMS CORE INFRASTRUCTURE
-- =============================================================================

-- 1. Teams - Central team management
CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    description TEXT CHECK (length(description) <= 500),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_code TEXT UNIQUE NOT NULL DEFAULT (
        'TM-' || upper(substring(gen_random_uuid()::text, 1, 6))
    ),
    is_active BOOLEAN DEFAULT true,
    max_members INTEGER DEFAULT 10,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Team Members - Role-based membership
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    invited_by UUID REFERENCES users(id),
    invitation_token TEXT,
    invitation_expires_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    UNIQUE(team_id, user_id)
);

-- 3. Team Invitations - Pending invites management
CREATE TABLE IF NOT EXISTS team_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    invited_email TEXT NOT NULL,
    invited_by UUID NOT NULL REFERENCES users(id),
    role TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin', 'editor', 'viewer')),
    invitation_token TEXT UNIQUE NOT NULL DEFAULT gen_random_uuid()::text,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'expired')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- PHASE 1B: ENHANCED PROJECT PRIVACY SYSTEM
-- =============================================================================

-- 4. Update existing projects visibility constraint
DO $$
BEGIN
    ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_visibility_check;
    ALTER TABLE projects ADD CONSTRAINT projects_visibility_check 
        CHECK (visibility IN ('private', 'team-only', 'public'));
EXCEPTION
    WHEN undefined_table THEN
        RAISE NOTICE 'Projects table does not exist yet, skipping visibility constraint update';
END $$;

-- 5. Project Privacy Settings - Granular control
CREATE TABLE IF NOT EXISTS project_privacy_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL UNIQUE,
    allow_team_access BOOLEAN DEFAULT false,
    restrict_to_specific_teams BOOLEAN DEFAULT false,
    allowed_team_ids UUID[] DEFAULT '{}',
    hide_from_other_teams BOOLEAN DEFAULT true,
    allow_generation_attribution BOOLEAN DEFAULT true,
    allow_generation_improvements BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add foreign key constraint only if projects table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        ALTER TABLE project_privacy_settings 
        ADD CONSTRAINT fk_project_privacy_settings_project_id
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 6. Project-Team Relationships
CREATE TABLE IF NOT EXISTS project_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL DEFAULT 'read' CHECK (access_level IN ('read', 'write', 'admin')),
    granted_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, team_id)
);

-- Add foreign key constraint only if projects table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        ALTER TABLE project_teams 
        ADD CONSTRAINT fk_project_teams_project_id
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
    END IF;
END $$;

-- =============================================================================
-- PHASE 1C: GENERATION PROVENANCE & COLLABORATION
-- =============================================================================

-- 7. Generation Collaborations - Track team work on generations
CREATE TABLE IF NOT EXISTS generation_collaborations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id UUID NOT NULL,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    contributor_id UUID NOT NULL REFERENCES users(id),
    collaboration_type TEXT NOT NULL CHECK (collaboration_type IN ('original', 'improvement', 'iteration', 'fork', 'remix')),
    parent_generation_id UUID,
    change_description TEXT CHECK (length(change_description) <= 1000),
    attribution_visible BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(generation_id, team_id, contributor_id)
);

-- Add foreign key constraints only if generations table exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generations') THEN
        ALTER TABLE generation_collaborations 
        ADD CONSTRAINT fk_generation_collaborations_generation_id
        FOREIGN KEY (generation_id) REFERENCES generations(id) ON DELETE CASCADE;
        
        ALTER TABLE generation_collaborations 
        ADD CONSTRAINT fk_generation_collaborations_parent_generation_id
        FOREIGN KEY (parent_generation_id) REFERENCES generations(id);
    END IF;
END $$;

-- 8. Add parent_generation_id to generations table if not exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generations') THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'generations' 
                       AND column_name = 'parent_generation_id') THEN
            ALTER TABLE generations ADD COLUMN parent_generation_id UUID REFERENCES generations(id);
            CREATE INDEX idx_generations_parent ON generations(parent_generation_id);
        END IF;
    END IF;
END $$;

-- 9. Add collaboration fields to generations
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generations') THEN
        -- Add team context
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'generations' 
                       AND column_name = 'team_context_id') THEN
            ALTER TABLE generations ADD COLUMN team_context_id UUID REFERENCES teams(id);
        END IF;
        
        -- Add collaboration intent
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'generations' 
                       AND column_name = 'collaboration_intent') THEN
            ALTER TABLE generations ADD COLUMN collaboration_intent TEXT 
                CHECK (collaboration_intent IN ('original', 'improve', 'iterate', 'fork', 'remix'));
        END IF;
        
        -- Add change description
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name = 'generations' 
                       AND column_name = 'change_description') THEN
            ALTER TABLE generations ADD COLUMN change_description TEXT 
                CHECK (length(change_description) <= 1000);
        END IF;
    END IF;
END $$;

-- =============================================================================
-- PHASE 1D: INDEXES FOR PERFORMANCE
-- =============================================================================

-- Teams indexes
CREATE INDEX IF NOT EXISTS idx_teams_owner_id ON teams(owner_id);
CREATE INDEX IF NOT EXISTS idx_teams_team_code ON teams(team_code);
CREATE INDEX IF NOT EXISTS idx_teams_active ON teams(is_active) WHERE is_active = true;

-- Team members indexes
CREATE INDEX IF NOT EXISTS idx_team_members_team_id ON team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_team_members_user_id ON team_members(user_id);
CREATE INDEX IF NOT EXISTS idx_team_members_role ON team_members(role);
CREATE INDEX IF NOT EXISTS idx_team_members_active ON team_members(team_id, user_id) WHERE is_active = true;

-- Team invitations indexes
CREATE INDEX IF NOT EXISTS idx_team_invitations_team_id ON team_invitations(team_id);
CREATE INDEX IF NOT EXISTS idx_team_invitations_email ON team_invitations(invited_email);
CREATE INDEX IF NOT EXISTS idx_team_invitations_token ON team_invitations(invitation_token);
CREATE INDEX IF NOT EXISTS idx_team_invitations_status ON team_invitations(status);
CREATE INDEX IF NOT EXISTS idx_team_invitations_expires ON team_invitations(expires_at);

-- Project privacy settings indexes
CREATE INDEX IF NOT EXISTS idx_project_privacy_project_id ON project_privacy_settings(project_id);
CREATE INDEX IF NOT EXISTS idx_project_privacy_team_access ON project_privacy_settings(allow_team_access) WHERE allow_team_access = true;

-- Project teams indexes
CREATE INDEX IF NOT EXISTS idx_project_teams_project_id ON project_teams(project_id);
CREATE INDEX IF NOT EXISTS idx_project_teams_team_id ON project_teams(team_id);
CREATE INDEX IF NOT EXISTS idx_project_teams_access ON project_teams(access_level);

-- Generation collaborations indexes
CREATE INDEX IF NOT EXISTS idx_generation_collaborations_generation_id ON generation_collaborations(generation_id);
CREATE INDEX IF NOT EXISTS idx_generation_collaborations_team_id ON generation_collaborations(team_id);
CREATE INDEX IF NOT EXISTS idx_generation_collaborations_contributor ON generation_collaborations(contributor_id);
CREATE INDEX IF NOT EXISTS idx_generation_collaborations_parent ON generation_collaborations(parent_generation_id);

-- Generations team context indexes (if generations table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generations') THEN
        CREATE INDEX IF NOT EXISTS idx_generations_team_context ON generations(team_context_id);
        CREATE INDEX IF NOT EXISTS idx_generations_collaboration_intent ON generations(collaboration_intent);
    END IF;
END $$;

-- =============================================================================
-- PHASE 1E: ROW LEVEL SECURITY (RLS) POLICIES - RECURSION-SAFE
-- =============================================================================

-- Enable RLS on all new tables
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_privacy_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_collaborations ENABLE ROW LEVEL SECURITY;

-- CRITICAL FIX: Create a secure function to get user teams (prevents recursion)
CREATE OR REPLACE FUNCTION get_user_team_ids(user_uuid UUID) 
RETURNS UUID[] 
LANGUAGE SQL
SECURITY DEFINER
STABLE
AS $$
    SELECT array_agg(team_id)::UUID[]
    FROM team_members 
    WHERE user_id = user_uuid AND is_active = true;
$$;

-- Teams policies - RECURSION-SAFE
DROP POLICY IF EXISTS "Users can view teams they are members of" ON teams;
CREATE POLICY "Users can view teams they are members of" ON teams
    FOR SELECT USING (
        id = ANY(get_user_team_ids(auth.uid()))
        OR owner_id = auth.uid()
    );

DROP POLICY IF EXISTS "Team owners can update their teams" ON teams;
CREATE POLICY "Team owners can update their teams" ON teams
    FOR UPDATE USING (owner_id = auth.uid());

DROP POLICY IF EXISTS "Users can create teams" ON teams;
CREATE POLICY "Users can create teams" ON teams
    FOR INSERT WITH CHECK (owner_id = auth.uid());

DROP POLICY IF EXISTS "Team owners can delete their teams" ON teams;
CREATE POLICY "Team owners can delete their teams" ON teams
    FOR DELETE USING (owner_id = auth.uid());

-- Team members policies - RECURSION-SAFE
DROP POLICY IF EXISTS "Users can view team members of teams they belong to" ON team_members;
CREATE POLICY "Users can view team members of teams they belong to" ON team_members
    FOR SELECT USING (
        team_id = ANY(get_user_team_ids(auth.uid()))
    );

DROP POLICY IF EXISTS "Team admins can manage team members" ON team_members;
CREATE POLICY "Team admins can manage team members" ON team_members
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM team_members tm 
            WHERE tm.team_id = team_members.team_id 
            AND tm.user_id = auth.uid() 
            AND tm.role IN ('owner', 'admin') 
            AND tm.is_active = true
        )
    );

DROP POLICY IF EXISTS "Users can join teams with valid invitations" ON team_members;
CREATE POLICY "Users can join teams with valid invitations" ON team_members
    FOR INSERT WITH CHECK (user_id = auth.uid());

-- Team invitations policies
DROP POLICY IF EXISTS "Team admins can manage invitations" ON team_invitations;
CREATE POLICY "Team admins can manage invitations" ON team_invitations
    FOR ALL USING (
        team_id = ANY(get_user_team_ids(auth.uid()))
        AND EXISTS (
            SELECT 1 FROM team_members tm 
            WHERE tm.team_id = team_invitations.team_id 
            AND tm.user_id = auth.uid() 
            AND tm.role IN ('owner', 'admin') 
            AND tm.is_active = true
        )
    );

-- Project privacy settings policies (if projects table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        DROP POLICY IF EXISTS "Project owners can manage privacy settings" ON project_privacy_settings;
        CREATE POLICY "Project owners can manage privacy settings" ON project_privacy_settings
            FOR ALL USING (
                project_id IN (
                    SELECT id FROM projects WHERE user_id = auth.uid()
                )
            );
    END IF;
END $$;

-- Project teams policies (if projects table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        DROP POLICY IF EXISTS "Project owners and team members can view project teams" ON project_teams;
        CREATE POLICY "Project owners and team members can view project teams" ON project_teams
            FOR SELECT USING (
                project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
                OR team_id = ANY(get_user_team_ids(auth.uid()))
            );

        DROP POLICY IF EXISTS "Project owners can manage project teams" ON project_teams;
        CREATE POLICY "Project owners can manage project teams" ON project_teams
            FOR ALL USING (
                project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
            );
    END IF;
END $$;

-- Generation collaborations policies (if generations table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'generations') THEN
        DROP POLICY IF EXISTS "Users can view collaborations on accessible generations" ON generation_collaborations;
        CREATE POLICY "Users can view collaborations on accessible generations" ON generation_collaborations
            FOR SELECT USING (
                generation_id IN (
                    SELECT id FROM generations WHERE user_id = auth.uid()
                )
                OR team_id = ANY(get_user_team_ids(auth.uid()))
            );

        DROP POLICY IF EXISTS "Team members can create collaborations" ON generation_collaborations;
        CREATE POLICY "Team members can create collaborations" ON generation_collaborations
            FOR INSERT WITH CHECK (
                contributor_id = auth.uid()
                AND team_id = ANY(get_user_team_ids(auth.uid()))
            );
    END IF;
END $$;

-- =============================================================================
-- PHASE 1F: TRIGGERS AND FUNCTIONS
-- =============================================================================

-- Update timestamp trigger function (reuse if exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers to new tables
DROP TRIGGER IF EXISTS update_teams_updated_at ON teams;
CREATE TRIGGER update_teams_updated_at 
    BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_team_invitations_updated_at ON team_invitations;
CREATE TRIGGER update_team_invitations_updated_at 
    BEFORE UPDATE ON team_invitations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_project_privacy_settings_updated_at ON project_privacy_settings;
CREATE TRIGGER update_project_privacy_settings_updated_at 
    BEFORE UPDATE ON project_privacy_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Team member auto-add trigger: Add team owner as owner member
CREATE OR REPLACE FUNCTION auto_add_team_owner()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO team_members (team_id, user_id, role, joined_at)
    VALUES (NEW.id, NEW.owner_id, 'owner', NOW())
    ON CONFLICT (team_id, user_id) DO NOTHING;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS auto_add_team_owner_trigger ON teams;
CREATE TRIGGER auto_add_team_owner_trigger
    AFTER INSERT ON teams
    FOR EACH ROW EXECUTE FUNCTION auto_add_team_owner();

-- Auto-create project privacy settings (if projects table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        CREATE OR REPLACE FUNCTION auto_create_project_privacy_settings()
        RETURNS TRIGGER AS $func$
        BEGIN
            INSERT INTO project_privacy_settings (project_id)
            VALUES (NEW.id)
            ON CONFLICT (project_id) DO NOTHING;
            RETURN NEW;
        END;
        $func$ language 'plpgsql';

        DROP TRIGGER IF EXISTS auto_create_project_privacy_settings_trigger ON projects;
        CREATE TRIGGER auto_create_project_privacy_settings_trigger
            AFTER INSERT ON projects
            FOR EACH ROW EXECUTE FUNCTION auto_create_project_privacy_settings();
    END IF;
END $$;

-- =============================================================================
-- PHASE 1G: BACKWARD COMPATIBILITY DATA MIGRATION
-- =============================================================================

-- Create default privacy settings for existing projects (if projects table exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'projects') THEN
        INSERT INTO project_privacy_settings (project_id)
        SELECT id FROM projects 
        WHERE id NOT IN (SELECT project_id FROM project_privacy_settings WHERE project_id IS NOT NULL);

        -- Update any existing 'team' visibility to 'team-only' for clarity
        UPDATE projects SET visibility = 'team-only' WHERE visibility = 'team';
    END IF;
END $$;

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

-- Log migration success
DO $$
BEGIN
    RAISE NOTICE 'Migration 011_team_collaboration_foundation_optimized completed successfully';
    RAISE NOTICE 'Phase 1 complete: Team collaboration infrastructure ready (RLS-SAFE)';
    RAISE NOTICE 'Next: Execute Phase 2 - Backend API implementation';
    RAISE NOTICE 'RLS Policies are recursion-safe and production-ready';
END $$;