# Credit Processing Debug Strategy

## 🚨 Problem Summary
**Issue**: User `22cb3917-57f6-49c6-ac96-ec266570081b` shows a paradox:
- ✅ GET `/api/v1/credits/balance` → 200 OK (user found, credits retrieved)
- ❌ POST `/api/v1/generations` → "User not found" during credit processing

## 🔍 Enhanced Logging Implementation

### 1. Generation Service (services/generation_service.py)
**Added comprehensive logging in `create_generation` method:**

```python
# Credit check flow with detailed logging
🔍 [GENERATION] Starting credit check for user {user_id}, credits_required: {credits_required}
🔍 [GENERATION] User service imported successfully for user {user_id}
🔍 [GENERATION] Calling can_afford_generation for user {user_id}
🔍 [GENERATION] can_afford_generation result for user {user_id}: {can_afford}
✅ [GENERATION] Credit check passed for user {user_id}, proceeding with generation

# Credit deduction flow with detailed logging  
💳 [GENERATION] Starting credit deduction for user {user_id}, generation {created_generation.id}
🔍 [GENERATION] Calling user_service.deduct_credits for user {user_id}
✅ [GENERATION] Successfully deducted {credits_required} credits from user {user_id}
```

### 2. User Service (services/user_service.py)
**Added detailed logging in key methods:**

```python
# get_user_credits method
💳 [USER_SERVICE] Getting credits for user {user_id}
🔍 [USER_SERVICE] Calling user_repo.get_user_credits for user {user_id}
✅ [USER_SERVICE] Successfully retrieved {credits} credits for user {user_id}

# can_afford_generation method  
💳 [USER_SERVICE] Checking affordability for user {user_id}, required: {required_credits}
🔍 [USER_SERVICE] Calling user_repo.get_user_credits for affordability check
💳 [USER_SERVICE] Current balance for user {user_id}: {current_balance}, required: {required_credits}
✅ [USER_SERVICE] Affordability check for user {user_id}: {can_afford}

# deduct_credits method
💳 [USER_SERVICE] Starting credit deduction for user {user_id}, amount: {amount}
🔍 [USER_SERVICE] Checking current balance for user {user_id}
🔍 [USER_SERVICE] Calling user_repo.deduct_credits for user {user_id}
✅ [USER_SERVICE] Credits deducted successfully for user {user_id}
```

### 3. User Repository (repositories/user_repository.py)
**Added comprehensive logging in database operations:**

```python
# get_user_by_id method
👤 [USER_REPO] Getting user by ID: {user_id}
🔍 [USER_REPO] Executing query for user {user_id} with service_key=True
✅ [USER_REPO] User found in database for ID {user_id}
⚠️ [USER_REPO] User profile not found for ID {user_id}, attempting to create from auth data

# get_user_credits method
💳 [USER_REPO] Getting credits for user {user_id}
🔍 [USER_REPO] Executing credits query for user {user_id} with service_key=True
✅ [USER_REPO] Credits found for user {user_id}: {credits}
```

### 4. Database Layer (database.py)
**Added client context and operation logging:**

```python
# Client selection logging
🔑 [DATABASE] Using SERVICE client for {operation} on {table}
🔑 [DATABASE] Service client bypasses RLS, operation: {operation}, table: {table}
🔓 [DATABASE] Using ANON client for {operation} on {table}  
🔓 [DATABASE] Anon client subject to RLS, operation: {operation}, table: {table}

# Query execution logging
🔍 [DATABASE] Creating query for {operation} on {table}, filters: {filters}
🔍 [DATABASE] Executing SELECT query on {table}
✅ [DATABASE] SELECT result for {table}: {len(result.data)} rows
```

## 🎯 Debugging Strategy

### Phase 1: Trace Complete Flow
With the enhanced logging, we can now trace:

1. **Generation Request Flow**:
   - Generation service starts credit check
   - Calls user service methods
   - User service calls repository methods
   - Repository executes database queries
   - Database layer shows client selection (service vs anon)

2. **Credits Endpoint Flow** (working):
   - Direct call to user service
   - Repository database query
   - Database execution

### Phase 2: Compare Flows
**Key Questions to Answer:**
- Are both flows using the same database client?
- Are there differences in RLS context between the flows?
- Is the generation flow hitting a different code path?
- Are there race conditions or timing issues?

### Phase 3: Expected Log Pattern
**Successful Flow Should Show:**
```
🔍 [GENERATION] Starting credit check for user 22cb3917-57f6-49c6-ac96-ec266570081b
💳 [USER_SERVICE] Getting credits for user 22cb3917-57f6-49c6-ac96-ec266570081b  
👤 [USER_REPO] Getting user by ID: 22cb3917-57f6-49c6-ac96-ec266570081b
🔑 [DATABASE] Using SERVICE client for select on users
✅ [USER_REPO] User found in database for ID 22cb3917-57f6-49c6-ac96-ec266570081b
✅ [USER_SERVICE] Successfully retrieved {X} credits for user 22cb3917-57f6-49c6-ac96-ec266570081b
```

**Failure Pattern Will Show:**
```
🔍 [GENERATION] Starting credit check for user 22cb3917-57f6-49c6-ac96-ec266570081b
💳 [USER_SERVICE] Getting credits for user 22cb3917-57f6-49c6-ac96-ec266570081b
👤 [USER_REPO] Getting user by ID: 22cb3917-57f6-49c6-ac96-ec266570081b
🔑/🔓 [DATABASE] Using {CLIENT_TYPE} client for select on users
❌ [USER_REPO] Query result for user 22cb3917-57f6-49c6-ac96-ec266570081b: False
⚠️ [USER_REPO] User profile not found for ID 22cb3917-57f6-49c6-ac96-ec266570081b
```

## 🧪 Testing Plan

### Step 1: Deploy Enhanced Logging
- Deploy the enhanced logging to Railway
- Monitor logs for the next generation request failure

### Step 2: Compare Log Patterns  
- Compare successful credits endpoint logs vs failed generation logs
- Look for differences in:
  - Database client selection (service vs anon)
  - Query execution paths
  - RLS context
  - Error patterns

### Step 3: Identify Root Cause
Based on the logs, identify:
- **Client Context Issue**: Are different clients being used?
- **RLS Policy Issue**: Are RLS policies blocking access inconsistently?
- **Database State Issue**: Is there a database connection or state problem?
- **Timing Issue**: Is there a race condition between authentication and database access?

### Step 4: Targeted Fix
Once root cause is identified:
- **If Client Issue**: Ensure consistent service key usage
- **If RLS Issue**: Review and fix RLS policies  
- **If State Issue**: Add connection retry logic
- **If Timing Issue**: Add proper async coordination

## 🔧 Immediate Actions

1. **Deploy enhanced logging** (✅ DONE)
2. **Monitor next failure** - Watch for detailed log patterns
3. **Compare working vs failing flows** - Identify exact divergence point
4. **Apply targeted fix** based on log analysis

## 🚀 Success Criteria

The issue will be resolved when:
- Both credits endpoint AND generations endpoint show consistent user lookup success
- Enhanced logging shows identical database client usage patterns
- No more "User not found" errors for authenticated users
- Credit processing flows complete successfully end-to-end

## 📋 Log Analysis Checklist
- [ ] Check database client selection consistency
- [ ] Verify RLS context in both flows  
- [ ] Compare query execution patterns
- [ ] Identify where user lookup diverges
- [ ] Trace error propagation path
- [ ] Confirm service key usage throughout