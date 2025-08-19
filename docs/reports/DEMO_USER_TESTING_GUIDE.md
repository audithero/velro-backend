# Demo User Testing Guide

## ✅ Demo User Successfully Created and Configured

### 🎯 Demo Credentials
- **Email**: `demo@velro.app`
- **Password**: `velrodemo123`
- **Credits**: 1200 (sufficient for extensive testing)
- **Role**: viewer
- **Status**: Active and verified

### 🧪 Authentication Testing Results

#### ✅ Supabase Auth Status
- Demo user exists in Supabase Auth system
- Email confirmed and verified
- Password properly encrypted and set
- User ID: `22cb3917-57f6-49c6-ac96-ec266570081b`

#### ✅ Database Profile Status
- User profile exists in public.users table
- Credits balance: 1200 (ready for testing)
- Display name: "Demo User"
- Full name: "Demo User"
- Account is active

#### ✅ Authentication Flow
- ✅ Login with email/password works
- ✅ JWT token generation successful
- ✅ Token format: Bearer token with proper expiration
- ✅ User data properly retrieved and formatted

## 🔧 How to Test

### 1. Frontend Login Testing
Use these credentials in your frontend login form:
```
Email: demo@velro.app
Password: velrodemo123
```

### 2. API Testing with cURL
```bash
# Test login endpoint
curl -X POST https://your-backend-url/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@velro.app",
    "password": "velrodemo123"
  }'
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "22cb3917-57f6-49c6-ac96-ec266570081b",
    "email": "demo@velro.app",
    "display_name": "Demo User",
    "credits_balance": 1200,
    "role": "viewer"
  }
}
```

### 3. Testing Authenticated Endpoints
Use the token from login response:
```bash
# Test user profile endpoint
curl -X GET https://your-backend-url/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 4. Testing Credit Operations
The demo user has 1200 credits available for testing:
- Image generation costs vary by model
- User can test multiple generations
- Credits will be properly deducted

## 🛠️ Verification Scripts

### Run Authentication Test
```bash
# From the backend directory
python3 test_demo_supabase_auth.py
```

This script tests:
- Supabase connection
- User authentication
- Token generation
- User profile retrieval

## 🔒 Security Features Verified

- ✅ Password properly hashed with bcrypt
- ✅ JWT tokens with proper expiration (1 hour)
- ✅ Rate limiting applies to login attempts
- ✅ Input validation on authentication endpoints
- ✅ CORS protection configured

## 📊 User Capabilities

The demo user can:
- ✅ Login and receive valid JWT tokens
- ✅ Access authenticated endpoints
- ✅ Generate images (with credit deduction)
- ✅ View generation history
- ✅ Check credit balance
- ✅ Access profile information

## 🚨 Important Notes

1. **Credit Balance**: The user starts with 1200 credits
2. **Role**: Set to "viewer" - has standard user permissions
3. **Token Expiry**: JWT tokens expire after 1 hour
4. **Rate Limiting**: Login attempts are rate-limited (5/minute)
5. **Account Status**: Active and ready for immediate use

## 🎉 Ready for Testing

The demo user account is fully functional and ready for:
- Frontend authentication testing
- API endpoint testing  
- Image generation testing
- Credit system testing
- End-to-end workflow testing

**Happy Testing!** 🚀