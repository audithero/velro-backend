# Authentication API Documentation

## Overview

This document provides comprehensive API documentation for the Velro authentication system. All authentication endpoints are prefixed with `/api/v1/auth` and follow RESTful conventions with comprehensive security measures.

## Base URL

- **Production**: `https://velro-backend-production.up.railway.app/api/v1/auth`
- **Development**: `http://localhost:8000/api/v1/auth`

## Authentication

Most endpoints require a Bearer token in the Authorization header:

```
Authorization: Bearer <jwt_token>
```

## Rate Limiting

All endpoints are rate-limited for security. Limits are shown per endpoint below.

## Common Response Formats

### Success Response
```json
{
  "data": {},
  "message": "Operation successful",
  "timestamp": "2025-08-03T22:00:00Z"
}
```

### Error Response
```json
{
  "detail": "Error message",
  "status_code": 400,
  "timestamp": "2025-08-03T22:00:00Z"
}
```

## Endpoints

### 1. User Registration

Register a new user account.

**Endpoint**: `POST /auth/register`  
**Rate Limit**: 3 requests per minute  
**Authentication**: Not required

#### Request Body
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123",
  "full_name": "John Doe",
  "confirm_password": "SecurePassword123"  // Optional
}
```

#### Request Schema
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| email | string | Yes | Valid email format, max 254 chars |
| password | string | Yes | 8-128 chars, letters + numbers |
| full_name | string | No | 1-100 chars, letters/spaces/hyphens |
| confirm_password | string | No | Must match password |

#### Success Response (201 Created)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "display_name": "John Doe",
    "avatar_url": null,
    "credits_balance": 1000,
    "role": "viewer",
    "created_at": "2025-08-03T22:00:00Z"
  }
}
```

#### Error Responses
| Status | Description | Example |
|--------|-------------|---------|
| 400 | Validation error | Email already registered |
| 422 | Invalid input format | Invalid email format |
| 429 | Rate limit exceeded | Too many registration attempts |
| 500 | Server error | Registration service unavailable |

#### Example Request
```bash
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123",
    "full_name": "John Doe"
  }'
```

### 2. User Login

Authenticate an existing user.

**Endpoint**: `POST /auth/login`  
**Rate Limit**: 5 requests per minute  
**Authentication**: Not required

#### Request Body
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123",
  "remember_me": false  // Optional
}
```

#### Request Schema
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| email | string | Yes | Valid email format |
| password | string | Yes | Non-empty string |
| remember_me | boolean | No | Extends token lifetime |

#### Success Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "refresh_token": "refresh_token_here",  // If remember_me=true
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "display_name": "John Doe",
    "avatar_url": null,
    "credits_balance": 950,
    "role": "viewer",
    "created_at": "2025-08-03T22:00:00Z"
  }
}
```

#### Error Responses
| Status | Description | Example |
|--------|-------------|---------|
| 401 | Invalid credentials | Invalid email or password |
| 422 | Validation error | Email format invalid |
| 429 | Rate limit exceeded | Too many login attempts |
| 500 | Server error | Authentication service error |

#### Example Request
```bash
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123"
  }'
```

### 3. Get Current User

Get information about the currently authenticated user.

**Endpoint**: `GET /auth/me`  
**Rate Limit**: 60 requests per minute  
**Authentication**: Required

#### Request Headers
```
Authorization: Bearer <jwt_token>
```

#### Success Response (200 OK)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "display_name": "John Doe",
  "avatar_url": "https://example.com/avatar.jpg",
  "credits_balance": 950,
  "role": "viewer",
  "created_at": "2025-08-03T22:00:00Z",
  "updated_at": "2025-08-03T22:15:00Z"
}
```

#### Error Responses
| Status | Description | Example |
|--------|-------------|---------|
| 401 | Authentication required | Invalid or expired token |
| 429 | Rate limit exceeded | Too many requests |

#### Example Request
```bash
curl -X GET "https://velro-backend-production.up.railway.app/api/v1/auth/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 4. Token Refresh

Refresh an expired or expiring access token.

**Endpoint**: `POST /auth/refresh`  
**Rate Limit**: 10 requests per minute  
**Authentication**: Not required (uses refresh token)

#### Request Body
```json
{
  "refresh_token": "refresh_token_here"
}
```

#### Success Response (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "refresh_token": "new_refresh_token_here",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "display_name": "John Doe",
    "avatar_url": null,
    "credits_balance": 950,
    "role": "viewer",
    "created_at": "2025-08-03T22:00:00Z"
  }
}
```

#### Error Responses
| Status | Description | Example |
|--------|-------------|---------|
| 401 | Invalid refresh token | Token expired or invalid |
| 429 | Rate limit exceeded | Too many refresh attempts |

### 5. User Logout

Logout the current user and invalidate the token.

**Endpoint**: `POST /auth/logout`  
**Rate Limit**: 60 requests per minute  
**Authentication**: Required

#### Request Headers
```
Authorization: Bearer <jwt_token>
```

#### Success Response (200 OK)
```json
{
  "message": "Logout successful",
  "timestamp": 1691234567
}
```

#### Example Request
```bash
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/logout" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 6. Password Reset Request

Request a password reset email.

**Endpoint**: `POST /auth/password-reset`  
**Rate Limit**: 2 requests per minute  
**Authentication**: Not required

#### Request Body
```json
{
  "email": "user@example.com"
}
```

#### Success Response (200 OK)
```json
{
  "message": "Password reset email sent if account exists",
  "email": "user@example.com"
}
```

**Note**: This endpoint always returns success to prevent email enumeration attacks.

#### Example Request
```bash
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/password-reset" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com"
  }'
```

### 7. Password Reset Confirmation

Confirm password reset with token (requires Supabase Auth UI flow).

**Endpoint**: `POST /auth/password-reset-confirm`  
**Rate Limit**: 5 requests per minute  
**Authentication**: Not required

#### Request Body
```json
{
  "token": "reset_token_from_email",
  "new_password": "NewSecurePassword123",
  "confirm_password": "NewSecurePassword123"
}
```

#### Response (501 Not Implemented)
```json
{
  "detail": "Password reset confirmation requires client-side implementation with Supabase Auth UI"
}
```

**Note**: This endpoint is not fully implemented as it requires Supabase Auth UI integration on the frontend.

### 8. Update User Profile

Update the current user's profile information.

**Endpoint**: `PUT /auth/profile`  
**Rate Limit**: 60 requests per minute  
**Authentication**: Required

#### Request Headers
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

#### Request Body
```json
{
  "full_name": "John Smith",
  "avatar_url": "https://example.com/new-avatar.jpg"
}
```

#### Request Schema
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| full_name | string | No | 1-100 chars, letters/spaces/hyphens |
| avatar_url | string | No | Valid HTTPS URL |

#### Success Response (200 OK)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "display_name": "John Smith",
  "avatar_url": "https://example.com/new-avatar.jpg",
  "credits_balance": 950,
  "role": "viewer",
  "created_at": "2025-08-03T22:00:00Z",
  "updated_at": "2025-08-03T22:30:00Z"
}
```

#### Error Responses
| Status | Description | Example |
|--------|-------------|---------|
| 401 | Authentication required | Invalid token |
| 404 | User not found | User profile missing |
| 422 | Validation error | Invalid avatar URL |

### 9. Authentication Debug

Debug endpoint for testing authentication middleware.

**Endpoint**: `GET /auth/debug-auth`  
**Rate Limit**: 60 requests per minute  
**Authentication**: Optional

#### Success Response (200 OK)

With authentication:
```json
{
  "status": "authenticated",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "message": "Middleware authentication successful"
}
```

Without authentication:
```json
{
  "status": "not_authenticated",
  "message": "Middleware did not set user state",
  "auth_header_present": false,
  "request_path": "/api/v1/auth/debug-auth"
}
```

### 10. Security Information

Get information about security measures and rate limits.

**Endpoint**: `GET /auth/security-info`  
**Rate Limit**: 60 requests per minute  
**Authentication**: Not required

#### Success Response (200 OK)
```json
{
  "rate_limits": {
    "login": "5 attempts per minute",
    "register": "3 attempts per minute",
    "refresh": "10 attempts per minute",
    "password_reset": "2 requests per minute",
    "password_reset_confirm": "5 attempts per minute"
  },
  "security_features": [
    "JWT authentication",
    "Rate limiting",
    "Input validation",
    "Password strength requirements",
    "Email validation",
    "Request logging"
  ],
  "password_requirements": {
    "min_length": 8,
    "max_length": 128,
    "required": ["letters", "numbers"],
    "forbidden": ["common_passwords", "personal_info"]
  }
}
```

## Error Handling

### Standard Error Format
All errors follow the FastAPI standard format:

```json
{
  "detail": "Human-readable error message",
  "status_code": 400,
  "timestamp": "2025-08-03T22:00:00Z"
}
```

### Validation Errors (422)
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### Common HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful operation |
| 201 | Created | User registration success |
| 400 | Bad Request | General client error |
| 401 | Unauthorized | Authentication required/failed |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 422 | Unprocessable Entity | Validation error |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service down/overloaded |

## Authentication Flow Examples

### 1. Complete Registration Flow
```bash
# 1. Register new user
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "SecurePassword123",
    "full_name": "New User"
  }'

# Response includes access_token
# {
#   "access_token": "eyJ...",
#   "user": { ... }
# }

# 2. Use token for authenticated requests
curl -X GET "https://velro-backend-production.up.railway.app/api/v1/auth/me" \
  -H "Authorization: Bearer eyJ..."
```

### 2. Login and Profile Update Flow
```bash
# 1. Login existing user
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123"
  }'

# 2. Update profile with received token
curl -X PUT "https://velro-backend-production.up.railway.app/api/v1/auth/profile" \
  -H "Authorization: Bearer <received_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Updated Name",
    "avatar_url": "https://example.com/avatar.jpg"
  }'
```

### 3. Token Refresh Flow (if refresh tokens enabled)
```bash
# When access token expires, refresh it
curl -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "<refresh_token_from_login>"
  }'
```

## Security Considerations

### Token Storage
- Store tokens securely (HTTP-only cookies recommended)
- Never expose tokens in URLs or logs
- Implement automatic token refresh

### Rate Limiting
- Respect rate limits to avoid 429 errors
- Implement exponential backoff for retries
- Monitor rate limit headers

### Error Handling
- Never expose sensitive information in errors
- Log security events for monitoring
- Implement proper error recovery

### HTTPS Only
- Always use HTTPS in production
- Tokens are sensitive and must be encrypted in transit
- Validate SSL certificates

## Development and Testing

### Development Mode
When `DEVELOPMENT_MODE=true`:
- Mock authentication tokens available
- Relaxed security validations
- Debug endpoints enabled

### Testing Endpoints
Use the debug endpoint to test authentication:
```bash
curl -X GET "http://localhost:8000/api/v1/auth/debug-auth" \
  -H "Authorization: Bearer <test_token>"
```

### Mock Tokens (Development Only)
- Format: `mock_token_<user_id>`
- Example: `mock_token_550e8400-e29b-41d4-a716-446655440000`
- Only works in development mode

## Troubleshooting

### Common Issues

1. **401 Unauthorized**
   - Check token validity and expiration
   - Verify Authorization header format
   - Ensure token hasn't been blacklisted

2. **429 Rate Limited**
   - Reduce request frequency
   - Implement exponential backoff
   - Check rate limit windows

3. **422 Validation Error**
   - Verify request body format
   - Check required fields
   - Validate field constraints

4. **CORS Errors**
   - Ensure proper Origin header
   - Check allowed origins configuration
   - Verify preflight requests

### Debug Steps
1. Check endpoint availability: `/health`
2. Test authentication: `/auth/debug-auth`  
3. Verify security info: `/auth/security-info`
4. Check server logs for detailed errors
5. Validate environment configuration

This API documentation provides comprehensive coverage of all authentication endpoints with examples, error handling, and security considerations for production deployment.