-- Migration: Fix Generation Schema Mismatches
-- Purpose: Add missing columns expected by the code models
-- Date: 2025-07-21

-- Add missing columns expected by the code
ALTER TABLE generations 
ADD COLUMN IF NOT EXISTS parent_generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS media_url TEXT,
ADD COLUMN IF NOT EXISTS media_type TEXT,
ADD COLUMN IF NOT EXISTS cost INTEGER;

-- Add index for parent_generation_id relationships
CREATE INDEX IF NOT EXISTS idx_generations_parent_id ON generations(parent_generation_id);

-- Add comments for clarity
COMMENT ON COLUMN generations.parent_generation_id IS 'Reference to parent generation for variations/iterations';
COMMENT ON COLUMN generations.media_url IS 'Primary media URL (first item from output_urls)';
COMMENT ON COLUMN generations.media_type IS 'Media type classification (maps to generation_type)';
COMMENT ON COLUMN generations.cost IS 'Cost in credits (maps to credits_used)';

-- Update existing records to populate new fields from existing data
UPDATE generations 
SET 
    media_type = generation_type,
    cost = COALESCE(credits_used, 0),
    media_url = CASE 
        WHEN output_urls IS NOT NULL AND array_length(output_urls, 1) > 0 
        THEN output_urls[1] 
        ELSE NULL 
    END
WHERE media_type IS NULL OR cost IS NULL OR media_url IS NULL;