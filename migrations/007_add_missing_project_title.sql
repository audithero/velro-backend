-- Add missing title column to projects table to maintain compatibility
-- This fixes issues where legacy code expects both name and title fields

-- Add title column if it doesn't exist (idempotent)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'projects' AND column_name = 'title') THEN
        ALTER TABLE projects ADD COLUMN title TEXT;
        
        -- Copy name to title for existing records
        UPDATE projects SET title = name WHERE title IS NULL;
        
        -- Add constraint to ensure title is not null going forward
        ALTER TABLE projects ALTER COLUMN title SET NOT NULL;
        
        -- Add length constraint to match name column
        ALTER TABLE projects ADD CONSTRAINT projects_title_length CHECK (length(title) <= 100);
    END IF;
END $$;