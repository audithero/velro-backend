-- Remove team functionality and fix RLS policy issues
-- Following CLAUDE.md: Security-first approach with proper RLS

-- Update projects table visibility constraint to remove 'team' option
ALTER TABLE projects 
DROP CONSTRAINT IF EXISTS projects_visibility_check;

ALTER TABLE projects 
ADD CONSTRAINT projects_visibility_check 
CHECK (visibility IN ('private', 'public'));

-- Update any existing 'team' visibility projects to 'private'
UPDATE projects 
SET visibility = 'private' 
WHERE visibility = 'team';

-- Add comment to clarify the change
COMMENT ON COLUMN projects.visibility IS 'Project visibility: private (owner only), public (visible to all)';