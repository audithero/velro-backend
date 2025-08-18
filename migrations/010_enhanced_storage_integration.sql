-- Enhanced Storage Integration Migration
-- Add storage-related fields and improve generation tracking

-- Add storage-related columns to generations table
ALTER TABLE generations 
ADD COLUMN IF NOT EXISTS storage_size BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_media_processed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS media_files JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS storage_metadata JSONB DEFAULT '{}'::jsonb;

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_generations_storage_size ON generations(storage_size);
CREATE INDEX IF NOT EXISTS idx_generations_is_media_processed ON generations(is_media_processed);
CREATE INDEX IF NOT EXISTS idx_generations_media_files ON generations USING GIN(media_files);
CREATE INDEX IF NOT EXISTS idx_generations_storage_metadata ON generations USING GIN(storage_metadata);

-- Add storage validation trigger
CREATE OR REPLACE FUNCTION validate_generation_storage_data()
RETURNS TRIGGER AS $$
BEGIN
    -- Validate storage_size is non-negative
    IF NEW.storage_size < 0 THEN
        RAISE EXCEPTION 'Storage size cannot be negative';
    END IF;
    
    -- Validate media_files is valid JSON array
    IF NEW.media_files IS NOT NULL AND jsonb_typeof(NEW.media_files) != 'array' THEN
        RAISE EXCEPTION 'media_files must be a JSON array';
    END IF;
    
    -- Validate storage_metadata is valid JSON object
    IF NEW.storage_metadata IS NOT NULL AND jsonb_typeof(NEW.storage_metadata) != 'object' THEN
        RAISE EXCEPTION 'storage_metadata must be a JSON object';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for storage validation
DROP TRIGGER IF EXISTS trigger_validate_generation_storage ON generations;
CREATE TRIGGER trigger_validate_generation_storage
    BEFORE INSERT OR UPDATE ON generations
    FOR EACH ROW
    EXECUTE FUNCTION validate_generation_storage_data();

-- Create function to get generation storage statistics
CREATE OR REPLACE FUNCTION get_user_storage_stats(user_uuid UUID)
RETURNS TABLE (
    total_generations BIGINT,
    total_storage_bytes BIGINT,
    processed_generations BIGINT,
    unprocessed_generations BIGINT,
    average_file_size NUMERIC,
    largest_generation_size BIGINT,
    total_media_files BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_generations,
        COALESCE(SUM(g.storage_size), 0)::BIGINT as total_storage_bytes,
        COUNT(*) FILTER (WHERE g.is_media_processed = true)::BIGINT as processed_generations,
        COUNT(*) FILTER (WHERE g.is_media_processed = false)::BIGINT as unprocessed_generations,
        CASE 
            WHEN COUNT(*) > 0 THEN COALESCE(AVG(g.storage_size), 0)
            ELSE 0
        END as average_file_size,
        COALESCE(MAX(g.storage_size), 0)::BIGINT as largest_generation_size,
        COALESCE(SUM(jsonb_array_length(g.media_files)), 0)::BIGINT as total_media_files
    FROM generations g
    WHERE g.user_id = user_uuid
    AND g.status = 'completed';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to cleanup orphaned storage references
CREATE OR REPLACE FUNCTION cleanup_orphaned_storage_references()
RETURNS INTEGER AS $$
DECLARE
    cleanup_count INTEGER := 0;
BEGIN
    -- This function would typically coordinate with the storage service
    -- to remove references to files that no longer exist in storage
    
    -- Update generations with empty media_files if storage validation fails
    UPDATE generations 
    SET 
        media_files = '[]'::jsonb,
        storage_metadata = jsonb_set(
            COALESCE(storage_metadata, '{}'::jsonb),
            '{cleanup_performed}',
            'true'::jsonb
        ),
        storage_metadata = jsonb_set(
            storage_metadata,
            '{cleanup_timestamp}',
            to_jsonb(CURRENT_TIMESTAMP::text)
        )
    WHERE status = 'failed' 
    AND media_files != '[]'::jsonb
    AND updated_at < CURRENT_TIMESTAMP - INTERVAL '24 hours';
    
    GET DIAGNOSTICS cleanup_count = ROW_COUNT;
    
    RETURN cleanup_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add RLS policies for new columns
-- The existing RLS policies on generations table will automatically apply to new columns

-- Create view for generation storage information
CREATE OR REPLACE VIEW generation_storage_info AS
SELECT 
    g.id,
    g.user_id,
    g.status,
    g.storage_size,
    g.is_media_processed,
    jsonb_array_length(g.media_files) as media_files_count,
    g.storage_metadata,
    g.created_at,
    g.updated_at,
    -- Extract useful metadata
    (g.storage_metadata->>'storage_successful')::boolean as storage_successful,
    (g.storage_metadata->>'supabase_urls_used')::boolean as supabase_urls_used,
    g.storage_metadata->>'files_stored' as files_stored,
    g.storage_metadata->>'total_size' as metadata_total_size
FROM generations g
WHERE g.status = 'completed';

-- Grant permissions for the view
GRANT SELECT ON generation_storage_info TO authenticated;

-- Add helpful comments
COMMENT ON COLUMN generations.storage_size IS 'Total size in bytes of all stored files for this generation';
COMMENT ON COLUMN generations.is_media_processed IS 'Whether media files have been fully processed and stored';
COMMENT ON COLUMN generations.media_files IS 'Array of media file metadata including file_id, path, size, etc.';
COMMENT ON COLUMN generations.storage_metadata IS 'Additional storage-related metadata and processing information';

COMMENT ON FUNCTION get_user_storage_stats(UUID) IS 'Get comprehensive storage statistics for a user';
COMMENT ON FUNCTION cleanup_orphaned_storage_references() IS 'Clean up references to storage files that no longer exist';
COMMENT ON VIEW generation_storage_info IS 'Consolidated view of generation storage information';

-- Create notification function for storage events
CREATE OR REPLACE FUNCTION notify_storage_event()
RETURNS TRIGGER AS $$
BEGIN
    -- Notify when storage processing completes
    IF OLD.is_media_processed = false AND NEW.is_media_processed = true THEN
        PERFORM pg_notify(
            'storage_processed',
            json_build_object(
                'generation_id', NEW.id,
                'user_id', NEW.user_id,
                'storage_size', NEW.storage_size,
                'media_files_count', jsonb_array_length(NEW.media_files)
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for storage event notifications
DROP TRIGGER IF EXISTS trigger_notify_storage_event ON generations;
CREATE TRIGGER trigger_notify_storage_event
    AFTER UPDATE ON generations
    FOR EACH ROW
    EXECUTE FUNCTION notify_storage_event();

-- Migration complete
SELECT 'Enhanced storage integration migration completed successfully' as status;