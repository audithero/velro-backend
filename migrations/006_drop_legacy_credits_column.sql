-- Migration to drop legacy 'credits' column from users table
-- The system now exclusively uses 'credits_balance' column
-- Date: 2025-08-01
-- Description: Remove legacy credits column after confirming all code uses credits_balance

-- First, let's ensure all users have proper credits_balance values
-- Copy any remaining credits data to credits_balance if needed
UPDATE users 
SET credits_balance = COALESCE(credits_balance, credits, 1000)
WHERE credits_balance IS NULL OR credits_balance = 0;

-- Ensure no user has a null credits_balance
UPDATE users 
SET credits_balance = 1000 
WHERE credits_balance IS NULL;

-- Add constraint to ensure credits_balance is never null
ALTER TABLE users ALTER COLUMN credits_balance SET NOT NULL;

-- Drop the legacy credits column
ALTER TABLE users DROP COLUMN IF EXISTS credits;

-- Add a comment to document the change
COMMENT ON COLUMN users.credits_balance IS 'User credit balance - primary credit tracking column (legacy credits column removed in migration 006)';