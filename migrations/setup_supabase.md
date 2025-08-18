# Supabase Setup Instructions

## Prerequisites
1. Create a Supabase project at https://supabase.com
2. Install Supabase CLI: `npm install -g supabase`

## Setup Steps

### 1. Initialize Supabase in your project
```bash
cd velro-backend
supabase init
```

### 2. Link to your Supabase project
```bash
supabase link --project-ref YOUR_PROJECT_REF
```

### 3. Apply the initial schema
```bash
supabase db push
```

Or manually run the SQL in the Supabase dashboard:
1. Go to your Supabase project dashboard
2. Navigate to "SQL Editor"
3. Copy and paste the contents of `001_initial_schema.sql`
4. Click "Run"

### 4. Set up Storage buckets
In the Supabase dashboard, go to Storage and create these buckets:

1. **generations** (for generated images/videos)
   - Public: true
   - File size limit: 100MB
   - Allowed MIME types: image/*, video/*

2. **references** (for user-uploaded reference images)
   - Public: false
   - File size limit: 10MB
   - Allowed MIME types: image/*

### 5. Storage RLS Policies

Add these policies in Storage > Policies:

**For 'generations' bucket:**
```sql
-- Users can upload their own generations
CREATE POLICY "Users can upload generations" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'generations' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Users can view their own generations
CREATE POLICY "Users can view own generations" ON storage.objects
    FOR SELECT USING (bucket_id = 'generations' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Public read access for completed generations
CREATE POLICY "Public read access" ON storage.objects
    FOR SELECT USING (bucket_id = 'generations');
```

**For 'references' bucket:**
```sql
-- Users can upload reference images
CREATE POLICY "Users can upload references" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'references' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Users can view their own reference images
CREATE POLICY "Users can view own references" ON storage.objects
    FOR SELECT USING (bucket_id = 'references' AND auth.uid()::text = (storage.foldername(name))[1]);
```

### 6. Set up Auth
In Authentication > Settings:
1. Enable email confirmation: false (for development)
2. Enable email change confirmation: true
3. Enable secure password change: true

### 7. Environment Variables
Add these to your environment:

**Backend (.env):**
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
```

**Frontend (.env.local):**
```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Verification
After setup, verify by:
1. Creating a test user through the frontend
2. Checking that the user appears in the `users` table
3. Creating a test project
4. Verifying RLS policies work by switching users

## Database Schema Overview

### Core Tables:
- **users**: User profiles with credits and metadata
- **projects**: User projects for organizing generations
- **ai_models**: Available AI models with pricing
- **style_stacks**: Reusable style presets
- **generations**: AI generation requests and results
- **credit_transactions**: Credit usage tracking

### Security Features:
- Row Level Security (RLS) on all tables
- User isolation (users can only access their own data)
- Public/private sharing controls
- Credit balance tracking and validation