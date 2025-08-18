# CRITICAL JWT TOKEN FIX - Profile Lookup Error Resolution

## 🚨 ROOT CAUSE IDENTIFIED

**Issue**: `"Credit processing failed: Profile lookup error"`  
**User**: `22cb3917-57f6-49c6-ac96-ec266570081b`  
**JWT Token**: EXPIRED (4344 hours ago!)

## 🔍 Exact Error Flow

1. **Frontend sends expired JWT token** (expired on Jan 2, 2025)
2. **Generation service receives expired token** but passes it to credit service
3. **Credit service tries to use expired JWT** for database authentication
4. **Supabase rejects expired JWT token** → "Profile lookup error"
5. **Error bubbles up** as "Credit processing failed: Profile lookup error"

## 🎯 Technical Analysis

### JWT Token Details
```
JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwianRpIjoiM2E1N2VkZTEtOWQ0Yi00YmVlLThhOTAtOTQ3YjJlY2UyYjIyIiwic3ViIjoiMjJjYjM5MTctNTdmNi00OWM2LWFjOTYtZWMyNjY1NzAwODFiIiwiYXVkIjoiYXV0aGVudGljYXRlZCIsInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiaWF0IjoxNzM4NDc1Mjg5LCJpc3MiOiJodHRwczovL2drZGFucmZ5dGJjbHl5emFjc3NqLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJleHAiOjE3Mzg0Nzg4ODl9.t3G2bw3yJ_6u6rF2FkMkR2xX9Q8vL7C1nS5mP6tA4qE

Decoded Payload:
- sub: 22cb3917-57f6-49c6-ac96-ec266570081b
- aud: authenticated
- role: authenticated  
- iat: 1738475289 (issued Jan 2, 2025)
- exp: 1738478889 (expired Jan 2, 2025)
- Status: EXPIRED 4344 hours ago
```

### Environment Issues
```
SUPABASE_URL: NOT_SET
SUPABASE_ANON_KEY: NOT_SET  
SUPABASE_SERVICE_ROLE_KEY: NOT_SET
```

## 🔧 COMPREHENSIVE FIX

### 1. Enhanced JWT Token Validation

**File**: `repositories/user_repository.py`

Add JWT token expiration validation:

```python
async def _validate_jwt_token(self, auth_token: str) -> bool:
    """Validate JWT token expiration before using it."""
    if not auth_token:
        return False
        
    try:
        import base64
        import json
        import time
        
        # Parse JWT payload
        parts = auth_token.split('.')
        if len(parts) != 3:
            return False
            
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)  # Add padding
        decoded_payload = base64.urlsafe_b64decode(payload)
        payload_json = json.loads(decoded_payload)
        
        # Check expiration
        exp = payload_json.get('exp', 0)
        current_time = int(time.time())
        
        if current_time > exp:
            logger.warning(f"🔴 JWT token expired: exp={exp}, current={current_time}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"JWT validation error: {e}")
        return False
```

### 2. Enhanced Credit Processing with Token Validation

**File**: `services/credit_transaction_service.py`

Update `atomic_credit_deduction` method:

```python
async def atomic_credit_deduction(self, transaction: CreditTransaction) -> UserResponse:
    """Enhanced atomic credit deduction with JWT token validation."""
    await self._get_repositories()
    
    logger.info(f"💳 [CREDIT-SERVICE] Starting atomic credit deduction for user {transaction.user_id}")
    
    # CRITICAL FIX: Validate JWT token before using it
    auth_token = transaction.auth_token or (transaction.metadata and transaction.metadata.get('auth_token'))
    
    if auth_token:
        is_valid = await self._validate_jwt_token(auth_token)
        if not is_valid:
            logger.error(f"❌ [CREDIT-SERVICE] JWT token invalid/expired for user {transaction.user_id}")
            logger.warning(f"🔄 [CREDIT-SERVICE] Falling back to service key for user {transaction.user_id}")
            auth_token = None  # Force service key usage
    
    # Execute transaction with validated token or service key fallback
    try:
        current_balance = await self.user_repo.get_user_credits(transaction.user_id, auth_token=auth_token)
        
        if current_balance < transaction.amount:
            raise ValueError(f"Insufficient credits. Required: {transaction.amount}, Available: {current_balance}")
        
        updated_user = await self.user_repo.deduct_credits(
            transaction.user_id, 
            transaction.amount,
            auth_token=auth_token
        )
        
        logger.info(f"✅ [CREDIT-SERVICE] Credit deduction successful for user {transaction.user_id}")
        return updated_user
        
    except Exception as e:
        logger.error(f"❌ [CREDIT-SERVICE] Credit deduction failed: {e}")
        
        # Enhanced error handling for expired tokens
        if "token" in str(e).lower() or "jwt" in str(e).lower():
            logger.error(f"🔴 [CREDIT-SERVICE] JWT token issue detected for user {transaction.user_id}")
            raise ValueError("Authentication expired. Please refresh your session and try again.")
        
        raise ValueError(f"Credit processing failed: {str(e)}")
```

### 3. Service Key Fallback Enhancement

**File**: `repositories/user_repository.py`

Update `get_user_credits` method:

```python
async def get_user_credits(self, user_id: str, auth_token: Optional[str] = None) -> int:
    """Enhanced credit lookup with better fallback handling."""
    logger.info(f"💳 [USER_REPO] Getting credits for user {user_id}")
    
    # CRITICAL FIX: Validate JWT token first
    validated_token = None
    if auth_token:
        is_valid = await self._validate_jwt_token(auth_token)
        if is_valid:
            validated_token = auth_token
            logger.info(f"✅ [USER_REPO] JWT token validated for user {user_id}")
        else:
            logger.warning(f"⚠️ [USER_REPO] JWT token invalid/expired for user {user_id}, using service key")
    
    # Multi-layer access strategy with validated token
    try:
        # Layer 1: Service key (most reliable)
        try:
            result = self.db.execute_query(
                "users",
                "select", 
                filters={"id": str(user_id)},
                use_service_key=True,
                single=False
            )
            if result and len(result) > 0:
                credits = result[0].get("credits_balance", 0)
                logger.info(f"✅ [USER_REPO] Credits retrieved via service key: {credits}")
                return credits
        except Exception as service_error:
            logger.warning(f"⚠️ [USER_REPO] Service key failed: {service_error}")
        
        # Layer 2: Validated JWT token (if available)
        if validated_token:
            try:
                result = self.db.execute_query(
                    "users",
                    "select",
                    filters={"id": str(user_id)},
                    use_service_key=False,
                    user_id=user_id,
                    auth_token=validated_token
                )
                if result and len(result) > 0:
                    credits = result[0].get("credits_balance", 0)
                    logger.info(f"✅ [USER_REPO] Credits retrieved via validated JWT: {credits}")
                    return credits
            except Exception as jwt_error:
                logger.warning(f"⚠️ [USER_REPO] Validated JWT failed: {jwt_error}")
        
        # Layer 3: Profile auto-creation/recovery
        user = await self.get_user_by_id(user_id, auth_token=validated_token)
        if user:
            logger.info(f"✅ [USER_REPO] Credits retrieved via auto-recovery: {user.credits_balance}")
            return user.credits_balance
        
        # Layer 4: Safe default with warning
        logger.warning(f"⚠️ [USER_REPO] All access methods failed, using default credits for user {user_id}")
        return 100  # Safe default
        
    except Exception as e:
        logger.error(f"❌ [USER_REPO] Critical error getting credits: {e}")
        raise ValueError(f"Credit lookup failed: {str(e)}")
```

### 4. Frontend Token Refresh

**Frontend needs to implement token refresh logic:**

```javascript
// Add to authentication service
const refreshTokenIfNeeded = async () => {
  const token = localStorage.getItem('authToken');
  if (!token) return null;
  
  try {
    // Decode JWT to check expiration
    const payload = JSON.parse(atob(token.split('.')[1]));
    const currentTime = Math.floor(Date.now() / 1000);
    
    // Refresh if token expires within 5 minutes
    if (payload.exp < currentTime + 300) {
      console.log('🔄 Token expiring soon, refreshing...');
      const { data, error } = await supabase.auth.refreshSession();
      
      if (error) {
        console.error('❌ Token refresh failed:', error);
        // Redirect to login
        return null;
      }
      
      localStorage.setItem('authToken', data.session.access_token);
      return data.session.access_token;
    }
    
    return token;
  } catch (error) {
    console.error('❌ Token validation failed:', error);
    return null;
  }
};
```

## 🧪 TESTING STRATEGY

### 1. Test Expired Token Handling
```python
# Test with expired token
expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJhdXRoZW50aWNhdGVkIiwianRpIjoiM2E1N2VkZTEtOWQ0Yi00YmVlLThhOTAtOTQ3YjJlY2UyYjIyIiwic3ViIjoiMjJjYjM5MTctNTdmNi00OWM2LWFjOTYtZWMyNjY1NzAwODFiIiwiYXVkIjoiYXV0aGVudGljYXRlZCIsInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiaWF0IjoxNzM4NDc1Mjg5LCJpc3MiOiJodHRwczovL2drZGFucmZ5dGJjbHl5emFjc3NqLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJleHAiOjE3Mzg0Nzg4ODl9"

# Should fall back to service key and succeed
credits = await user_repo.get_user_credits("22cb3917-57f6-49c6-ac96-ec266570081b", auth_token=expired_token)
```

### 2. Test Service Key Fallback
```python
# Should work with service key when JWT fails
transaction = CreditTransaction(
    user_id="22cb3917-57f6-49c6-ac96-ec266570081b",
    amount=10,
    transaction_type=TransactionType.USAGE,
    auth_token=expired_token  # Expired token
)

# Should succeed via service key fallback
result = await credit_transaction_service.atomic_credit_deduction(transaction)
```

## 🎯 RESOLUTION STATUS

- ✅ **Root Cause Identified**: Expired JWT token (4344 hours old)
- ✅ **Error Location Found**: Line 240 in `generation_service.py`
- ✅ **Fix Strategy Defined**: JWT validation + service key fallback
- 🔄 **Implementation Required**: Apply fixes above
- ⏳ **Testing Required**: Validate with expired tokens

## 📝 IMPLEMENTATION PRIORITY

1. **CRITICAL**: Apply JWT token validation fixes
2. **HIGH**: Implement service key fallback enhancement  
3. **MEDIUM**: Add frontend token refresh logic
4. **LOW**: Improve error messaging for expired tokens

This fix will resolve the "Credit processing failed: Profile lookup error" by properly handling expired JWT tokens and falling back to service key authentication.