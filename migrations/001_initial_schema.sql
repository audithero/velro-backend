-- Initial database schema for Velro platform
-- Following CLAUDE.md security checklist: RLS on all tables, RBAC checks

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table (auth.users is managed by Supabase Auth)
-- This is our custom user profile table
CREATE TABLE users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT true,
    credits_balance INTEGER DEFAULT 1000,
    current_plan TEXT DEFAULT 'free',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) <= 100),
    description TEXT CHECK (length(description) <= 500),
    visibility TEXT DEFAULT 'private' CHECK (visibility IN ('private', 'team', 'public')),
    tags TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    generation_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI Models table for available generation models
CREATE TABLE ai_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    generation_type TEXT NOT NULL CHECK (generation_type IN ('image', 'video', 'audio')),
    credits_cost INTEGER NOT NULL,
    description TEXT,
    parameters JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Style Stacks table
CREATE TABLE style_stacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (length(name) <= 100),
    description TEXT CHECK (length(description) <= 500),
    parameters JSONB DEFAULT '{}',
    is_public BOOLEAN DEFAULT false,
    is_featured BOOLEAN DEFAULT false,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Generations table
CREATE TABLE generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    model_id TEXT NOT NULL REFERENCES ai_models(id),
    style_stack_id UUID REFERENCES style_stacks(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),
    generation_type TEXT NOT NULL CHECK (generation_type IN ('image', 'video', 'audio')),
    prompt TEXT NOT NULL CHECK (length(prompt) <= 2000),
    negative_prompt TEXT CHECK (length(negative_prompt) <= 1000),
    reference_image_url TEXT,
    parameters JSONB DEFAULT '{}',
    output_urls TEXT[] DEFAULT '{}',
    credits_used INTEGER,
    processing_time FLOAT,
    error_message TEXT,
    is_favorite BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Credit transactions table for tracking credit usage
CREATE TABLE credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_id UUID REFERENCES generations(id) ON DELETE SET NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('purchase', 'usage', 'refund', 'bonus')),
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ai_models_updated_at BEFORE UPDATE ON ai_models
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_style_stacks_updated_at BEFORE UPDATE ON style_stacks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_generations_updated_at BEFORE UPDATE ON generations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Project generation counter trigger
CREATE OR REPLACE FUNCTION update_project_generation_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE projects 
        SET generation_count = generation_count + 1 
        WHERE id = NEW.project_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE projects 
        SET generation_count = generation_count - 1 
        WHERE id = OLD.project_id AND generation_count > 0;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_project_generation_count_trigger
    AFTER INSERT OR DELETE ON generations
    FOR EACH ROW EXECUTE FUNCTION update_project_generation_count();

-- Enable RLS on all tables (CLAUDE.md security requirement)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE style_stacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_transactions ENABLE ROW LEVEL SECURITY;

-- RLS Policies for users table
CREATE POLICY "Users can view own profile" ON users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON users
    FOR UPDATE USING (auth.uid() = id);

-- RLS Policies for projects table
CREATE POLICY "Users can view own projects" ON projects
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own projects" ON projects
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects" ON projects
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects" ON projects
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view public projects" ON projects
    FOR SELECT USING (visibility = 'public');

-- RLS Policies for ai_models table (read-only for users)
CREATE POLICY "All users can view active models" ON ai_models
    FOR SELECT USING (is_active = true);

-- RLS Policies for style_stacks table
CREATE POLICY "Users can view own style stacks" ON style_stacks
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own style stacks" ON style_stacks
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own style stacks" ON style_stacks
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own style stacks" ON style_stacks
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view public style stacks" ON style_stacks
    FOR SELECT USING (is_public = true);

CREATE POLICY "Users can view featured style stacks" ON style_stacks
    FOR SELECT USING (is_featured = true);

-- RLS Policies for generations table
CREATE POLICY "Users can view own generations" ON generations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own generations" ON generations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own generations" ON generations
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own generations" ON generations
    FOR DELETE USING (auth.uid() = user_id);

-- RLS Policies for credit_transactions table
CREATE POLICY "Users can view own credit transactions" ON credit_transactions
    FOR SELECT USING (auth.uid() = user_id);

-- Create indexes for performance
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_projects_visibility ON projects(visibility);
CREATE INDEX idx_projects_created_at ON projects(created_at DESC);

CREATE INDEX idx_generations_user_id ON generations(user_id);
CREATE INDEX idx_generations_project_id ON generations(project_id);
CREATE INDEX idx_generations_status ON generations(status);
CREATE INDEX idx_generations_created_at ON generations(created_at DESC);
CREATE INDEX idx_generations_model_id ON generations(model_id);

CREATE INDEX idx_style_stacks_user_id ON style_stacks(user_id);
CREATE INDEX idx_style_stacks_public ON style_stacks(is_public) WHERE is_public = true;
CREATE INDEX idx_style_stacks_featured ON style_stacks(is_featured) WHERE is_featured = true;

CREATE INDEX idx_credit_transactions_user_id ON credit_transactions(user_id);
CREATE INDEX idx_credit_transactions_created_at ON credit_transactions(created_at DESC);

-- Insert default AI models
INSERT INTO ai_models (id, name, generation_type, credits_cost, description, parameters) VALUES
('fal-ai/flux-pro', 'Flux Pro', 'image', 50, 'High-quality image generation with exceptional detail', '{"image_size": "landscape_16_9", "num_images": 1}'),
('fal-ai/flux-dev', 'Flux Dev', 'image', 25, 'Fast image generation for development and testing', '{"image_size": "landscape_16_9", "num_images": 1}'),
('fal-ai/veo3', 'Veo 3', 'video', 200, 'Advanced video generation with realistic motion', '{"duration": 5, "fps": 24}'),
('fal-ai/minimax', 'MiniMax Video', 'video', 150, 'Efficient video creation with good quality', '{"duration": 5, "fps": 24}'),
('fal-ai/kling-video', 'Kling Video', 'video', 180, 'Professional video generation', '{"duration": 5, "fps": 24}');

-- Insert default public style stacks
INSERT INTO style_stacks (id, user_id, name, description, is_public, is_featured, tags) VALUES
(gen_random_uuid(), NULL, 'Cyberpunk Neon', 'Futuristic cyberpunk aesthetic with vibrant neon colors and high-tech atmosphere', true, true, ARRAY['cyberpunk', 'neon', 'futuristic']),
(gen_random_uuid(), NULL, 'Natural Documentary', 'Clean, natural look perfect for documentary-style content', true, true, ARRAY['natural', 'documentary', 'clean']),
(gen_random_uuid(), NULL, 'Vintage Film', 'Classic vintage film look with grain and period-appropriate color grading', true, true, ARRAY['vintage', 'retro', 'film']),
(gen_random_uuid(), NULL, 'Cinematic Epic', 'Hollywood blockbuster style with dramatic lighting and composition', true, true, ARRAY['cinematic', 'epic', 'dramatic']),
(gen_random_uuid(), NULL, 'Anime Style', 'High-quality anime and manga inspired art style', true, true, ARRAY['anime', 'manga', 'japanese']);

-- RPC Functions for atomic operations

-- Atomic credit deduction function
CREATE OR REPLACE FUNCTION deduct_user_credits(user_id UUID, amount INTEGER)
RETURNS BOOLEAN AS $$
DECLARE
    current_balance INTEGER;
BEGIN
    -- Get current balance with row lock
    SELECT credits_balance INTO current_balance
    FROM users 
    WHERE id = user_id 
    FOR UPDATE;
    
    -- Check if user exists and has sufficient credits
    IF current_balance IS NULL THEN
        RETURN FALSE; -- User not found
    END IF;
    
    IF current_balance < amount THEN
        RETURN FALSE; -- Insufficient credits
    END IF;
    
    -- Deduct credits
    UPDATE users 
    SET credits_balance = credits_balance - amount,
        updated_at = NOW()
    WHERE id = user_id;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to add credits atomically
CREATE OR REPLACE FUNCTION add_user_credits(user_id UUID, amount INTEGER)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE users 
    SET credits_balance = credits_balance + amount,
        updated_at = NOW()
    WHERE id = user_id;
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- Function to get user's current credit balance
CREATE OR REPLACE FUNCTION get_user_credits(user_id UUID)
RETURNS INTEGER AS $$
DECLARE
    balance INTEGER;
BEGIN
    SELECT credits_balance INTO balance
    FROM users 
    WHERE id = user_id;
    
    RETURN COALESCE(balance, 0);
END;
$$ LANGUAGE plpgsql;