-- Fix missing RLS policies for credit_transactions table
-- This addresses the 42501 RLS policy violation error

-- Add missing INSERT policy for credit_transactions
-- Users should be able to insert their own credit transactions
CREATE POLICY "Users can create own credit transactions" ON credit_transactions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Add UPDATE policy for credit_transactions (for future use)
CREATE POLICY "Users can update own credit transactions" ON credit_transactions
    FOR UPDATE USING (auth.uid() = user_id);

-- Add DELETE policy for credit_transactions (for future use)  
CREATE POLICY "Users can delete own credit transactions" ON credit_transactions
    FOR DELETE USING (auth.uid() = user_id);