# 🚨 CRITICAL SUPABASE API KEY EMERGENCY FIX

## Issue Identified
The backend credit processing is failing with "Invalid API key" errors when trying to update user credits in Supabase. **The service role key is invalid or has been revoked.**

## Root Cause Analysis
1. ✅ **Anon key works**: Basic connections succeed
2. ❌ **Service role key fails**: All operations using `use_service_key=True` return 401 Unauthorized
3. ❌ **Credit operations fail**: Unable to update user credit balances
4. ❌ **Database writes fail**: All INSERT/UPDATE operations with service key fail

## Test Results
```
❌ Service key credit query failed: {'message': 'Invalid API key', 'hint': 'Double check your Supabase `anon` or `service_role` API key.'}
❌ Service key credit update failed: {'message': 'Invalid API key', 'hint': 'Double check your Supabase `anon` or `service_role` API key.'}
❌ Direct service key database update failed: {'message': 'Invalid API key', 'hint': 'Double check your Supabase `anon` or `service_role` API key.'}
```

## Immediate Actions Required

### 1. Verify Supabase Dashboard
- Login to https://supabase.com/dashboard
- Navigate to project: `ltspnsduziplpuqxczvy`
- Go to Settings → API
- Check if service_role key matches: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MjYzMzYxMSwiZXhwIjoyMDY4MjA5NjExfQ.F86OpY7O2mG7y0KJO2YDZVmvq8aFG8NTLMRO_rGp8ns`

### 2. Update Railway Environment Variables
If the service key is different in Supabase dashboard:

```bash
# Update Railway environment variables
railway variables set SUPABASE_SERVICE_ROLE_KEY="<new_service_key_from_dashboard>"
```

### 3. Alternative: Use Only Anon Key (Temporary Fix)
If service key cannot be fixed immediately, update the code to use anon key with proper RLS policies:

**File: `/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend/database.py`**

```python
# EMERGENCY FIX: Default to anon key if service key fails
def execute_query(self, ...):
    if use_service_key:
        try:
            client = self.service_client
            # ... existing service key logic
        except Exception as service_error:
            logger.warning(f"Service key failed, falling back to anon key: {service_error}")
            client = self.client
            use_service_key = False  # Force anon key usage
    else:
        client = self.client
```

### 4. Update RLS Policies (If Using Anon Key)
Ensure Supabase RLS policies allow authenticated users to update their own credits:

```sql
-- Policy for users to update their own credits
CREATE POLICY "Users can update own credits" ON users
FOR UPDATE USING (auth.uid()::text = id)
WITH CHECK (auth.uid()::text = id);
```

## Specific Code Files Affected

1. **`/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend/repositories/user_repository.py`**
   - All credit update operations (lines 263-341)
   - Service key operations failing

2. **`/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend/services/generation_service.py`**
   - Credit deduction in generation flow (lines 177-244)
   - Atomic credit operations failing

3. **`/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend/services/credit_transaction_service.py`**
   - All credit transaction operations (lines 202-298)
   - Service key dependency

## Environment Variables Check
Current configuration uses:
- `SUPABASE_URL`: https://ltspnsduziplpuqxczvy.supabase.co
- `SUPABASE_ANON_KEY`: Working ✅
- `SUPABASE_SERVICE_ROLE_KEY`: **INVALID** ❌

## Priority Actions
1. **IMMEDIATE**: Check Supabase dashboard for correct service role key
2. **URGENT**: Update Railway environment variables
3. **BACKUP**: Implement anon key fallback mechanism
4. **VERIFY**: Test credit operations after fix

## Testing Command
After fix, run:
```bash
python3 test_credit_api_key_error.py
```

Expected output should show:
```
✅ Service key credit query successful
✅ Service key credit update successful
✅ Atomic credit deduction successful
```