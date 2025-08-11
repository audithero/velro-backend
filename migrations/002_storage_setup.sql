-- Storage buckets and RLS policies for secure media management
-- Following CLAUDE.md: Secure storage with user isolation
-- Following PRD.MD: Fast, secure, cost-effective media storage

-- Enable storage extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "storage" SCHEMA "extensions";

-- Create storage buckets for organized media management
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES 
  -- Main bucket for AI generated content (private by default)
  ('velro-generations', 'velro-generations', false, 52428800, ARRAY[
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
    'video/mp4', 'video/webm', 'video/mov', 'video/avi'
  ]),
  
  -- Bucket for user uploaded reference images (private)
  ('velro-uploads', 'velro-uploads', false, 20971520, ARRAY[
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'
  ]),
  
  -- Bucket for optimized thumbnails (private, faster access)
  ('velro-thumbnails', 'velro-thumbnails', false, 2097152, ARRAY[
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp'
  ]),
  
  -- Bucket for temporary processing files (private, short-lived)
  ('velro-temp', 'velro-temp', false, 104857600, ARRAY[
    'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif',
    'video/mp4', 'video/webm', 'video/mov', 'video/avi'
  ])
ON CONFLICT (id) DO NOTHING;

-- Create file_metadata table to track file information
CREATE TABLE IF NOT EXISTS file_metadata (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  generation_id UUID REFERENCES generations(id) ON DELETE CASCADE,
  bucket_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  original_filename TEXT,
  file_size BIGINT NOT NULL,
  content_type TEXT NOT NULL,
  file_hash TEXT, -- For deduplication
  is_thumbnail BOOLEAN DEFAULT false,
  is_processed BOOLEAN DEFAULT false,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE, -- For temp files
  
  -- Constraints
  CONSTRAINT valid_bucket_name CHECK (bucket_name IN ('velro-generations', 'velro-uploads', 'velro-thumbnails', 'velro-temp')),
  CONSTRAINT valid_file_size CHECK (file_size > 0 AND file_size <= 104857600), -- Max 100MB
  CONSTRAINT valid_content_type CHECK (content_type ~ '^(image|video)/'),
  CONSTRAINT unique_user_file_path UNIQUE (user_id, bucket_name, file_path)
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_file_metadata_user_id ON file_metadata(user_id);
CREATE INDEX IF NOT EXISTS idx_file_metadata_generation_id ON file_metadata(generation_id);
CREATE INDEX IF NOT EXISTS idx_file_metadata_bucket_path ON file_metadata(bucket_name, file_path);
CREATE INDEX IF NOT EXISTS idx_file_metadata_hash ON file_metadata(file_hash) WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_file_metadata_expires ON file_metadata(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_file_metadata_created_at ON file_metadata(created_at);

-- Enable RLS on file_metadata table
ALTER TABLE file_metadata ENABLE ROW LEVEL SECURITY;

-- RLS Policies for file_metadata table
-- Users can only access their own file metadata
CREATE POLICY "Users can view their own file metadata" ON file_metadata
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own file metadata" ON file_metadata
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own file metadata" ON file_metadata
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own file metadata" ON file_metadata
  FOR DELETE USING (auth.uid() = user_id);

-- Storage RLS Policies for velro-generations bucket
-- Users can only access files in their user folder
CREATE POLICY "Users can view their own generation files" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'velro-generations' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can upload their own generation files" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'velro-generations' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can update their own generation files" ON storage.objects
  FOR UPDATE USING (
    bucket_id = 'velro-generations' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can delete their own generation files" ON storage.objects
  FOR DELETE USING (
    bucket_id = 'velro-generations' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

-- Storage RLS Policies for velro-uploads bucket
CREATE POLICY "Users can view their own upload files" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'velro-uploads' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can upload their own upload files" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'velro-uploads' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can update their own upload files" ON storage.objects
  FOR UPDATE USING (
    bucket_id = 'velro-uploads' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can delete their own upload files" ON storage.objects
  FOR DELETE USING (
    bucket_id = 'velro-uploads' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

-- Storage RLS Policies for velro-thumbnails bucket
CREATE POLICY "Users can view their own thumbnail files" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'velro-thumbnails' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can upload their own thumbnail files" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'velro-thumbnails' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can update their own thumbnail files" ON storage.objects
  FOR UPDATE USING (
    bucket_id = 'velro-thumbnails' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can delete their own thumbnail files" ON storage.objects
  FOR DELETE USING (
    bucket_id = 'velro-thumbnails' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

-- Storage RLS Policies for velro-temp bucket (stricter, time-limited)
CREATE POLICY "Users can view their own temp files" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'velro-temp' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1]) AND
    created_at > NOW() - INTERVAL '24 hours' -- Temp files expire after 24 hours
  );

CREATE POLICY "Users can upload their own temp files" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'velro-temp' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

CREATE POLICY "Users can delete their own temp files" ON storage.objects
  FOR DELETE USING (
    bucket_id = 'velro-temp' AND 
    (auth.uid()::text = (string_to_array(name, '/'))[1])
  );

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_file_metadata_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER update_file_metadata_updated_at_trigger
  BEFORE UPDATE ON file_metadata
  FOR EACH ROW
  EXECUTE FUNCTION update_file_metadata_updated_at();

-- Function to clean up expired temp files
CREATE OR REPLACE FUNCTION cleanup_expired_temp_files()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER := 0;
  temp_file RECORD;
BEGIN
  -- Delete expired file metadata records
  FOR temp_file IN 
    SELECT bucket_name, file_path 
    FROM file_metadata 
    WHERE bucket_name = 'velro-temp' 
    AND expires_at IS NOT NULL 
    AND expires_at < NOW()
  LOOP
    -- Delete from storage (this will be called via API)
    -- For now, just delete metadata - storage cleanup via cron job
    DELETE FROM file_metadata 
    WHERE bucket_name = temp_file.bucket_name 
    AND file_path = temp_file.file_path;
    
    deleted_count := deleted_count + 1;
  END LOOP;
  
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get user storage usage statistics
CREATE OR REPLACE FUNCTION get_user_storage_stats(target_user_id UUID)
RETURNS TABLE (
  bucket_name TEXT,
  file_count BIGINT,
  total_size BIGINT,
  avg_file_size NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    fm.bucket_name,
    COUNT(*)::BIGINT as file_count,
    SUM(fm.file_size)::BIGINT as total_size,
    AVG(fm.file_size)::NUMERIC as avg_file_size
  FROM file_metadata fm
  WHERE fm.user_id = target_user_id
  GROUP BY fm.bucket_name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to find duplicate files by hash
CREATE OR REPLACE FUNCTION find_duplicate_files(target_user_id UUID)
RETURNS TABLE (
  file_hash TEXT,
  file_count BIGINT,
  total_size BIGINT,
  file_paths TEXT[]
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    fm.file_hash,
    COUNT(*)::BIGINT as file_count,
    SUM(fm.file_size)::BIGINT as total_size,
    ARRAY_AGG(fm.bucket_name || '/' || fm.file_path) as file_paths
  FROM file_metadata fm
  WHERE fm.user_id = target_user_id
  AND fm.file_hash IS NOT NULL
  GROUP BY fm.file_hash
  HAVING COUNT(*) > 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Add storage-related columns to generations table
ALTER TABLE generations 
ADD COLUMN IF NOT EXISTS media_files JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS thumbnail_files JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS storage_size BIGINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS is_media_processed BOOLEAN DEFAULT false;

-- Create index for storage queries
CREATE INDEX IF NOT EXISTS idx_generations_media_processed ON generations(is_media_processed);

-- Comment on storage structure
COMMENT ON TABLE file_metadata IS 'Tracks file metadata for all storage buckets with user isolation';
COMMENT ON COLUMN file_metadata.file_hash IS 'SHA-256 hash for deduplication and integrity checking';
COMMENT ON COLUMN file_metadata.expires_at IS 'Expiration time for temporary files';
COMMENT ON COLUMN generations.media_files IS 'Array of media file metadata: [{bucket, path, size, type}]';
COMMENT ON COLUMN generations.thumbnail_files IS 'Array of thumbnail file metadata for quick loading';