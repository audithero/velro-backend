# CSRF Protection Frontend Integration Guide

This document provides comprehensive instructions for integrating CSRF protection with the React frontend.

## Overview

The Velro backend implements enterprise-grade CSRF (Cross-Site Request Forgery) protection using:
- **Double-submit cookie pattern**: Token must match both header/form field and secure cookie
- **Cryptographic token validation**: HMAC-signed tokens with timestamp and IP binding
- **Origin/Referer validation**: Additional layer of protection against cross-origin attacks
- **Time-based expiration**: Tokens expire after 2 hours for security

## Protected Endpoints

All state-changing HTTP methods are protected by CSRF validation:
- `POST` requests
- `PUT` requests  
- `DELETE` requests
- `PATCH` requests

**Exempt endpoints** (no CSRF required):
- Authentication endpoints (`/api/v1/auth/login`, `/api/v1/auth/register`, etc.)
- Health checks (`/health`, `/metrics`)
- GET requests (read-only operations)

## Frontend Implementation

### 1. CSRF Token Service

Create a service to manage CSRF tokens:

```typescript
// lib/csrf-service.ts
class CSRFService {
  private static token: string | null = null;
  private static tokenExpiry: number = 0;

  static async getCSRFToken(): Promise<string> {
    // Check if current token is still valid
    if (this.token && Date.now() < this.tokenExpiry) {
      return this.token;
    }

    try {
      const response = await fetch('/api/v1/security/csrf-token', {
        method: 'GET',
        credentials: 'include', // Important: Include cookies
      });

      if (!response.ok) {
        throw new Error(`CSRF token request failed: ${response.status}`);
      }

      const data = await response.json();
      this.token = data.csrf_token;
      this.tokenExpiry = Date.now() + (data.expires_in * 1000) - 60000; // 1 minute buffer
      
      return this.token;
    } catch (error) {
      console.error('Failed to fetch CSRF token:', error);
      throw error;
    }
  }

  static clearToken(): void {
    this.token = null;
    this.tokenExpiry = 0;
  }

  static async refreshToken(): Promise<string> {
    this.clearToken();
    return this.getCSRFToken();
  }
}

export default CSRFService;
```

### 2. API Client Integration

Update your API client to automatically include CSRF tokens:

```typescript
// lib/api-client.ts
import CSRFService from './csrf-service';

class APIClient {
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  private async makeRequest(
    endpoint: string, 
    options: RequestInit = {}
  ): Promise<Response> {
    const url = `${this.baseURL}${endpoint}`;
    
    // Add CSRF token for state-changing requests
    if (this.requiresCSRFToken(options.method || 'GET')) {
      try {
        const csrfToken = await CSRFService.getCSRFToken();
        
        // Set CSRF token in header
        options.headers = {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
          ...options.headers,
        };
      } catch (error) {
        console.error('Failed to get CSRF token:', error);
        throw new Error('CSRF token required but unavailable');
      }
    }

    // Always include credentials for cookie-based auth and CSRF
    options.credentials = 'include';

    const response = await fetch(url, options);
    
    // Handle CSRF token expiry
    if (response.status === 403 && this.isCSRFError(response)) {
      console.warn('CSRF token may be expired, refreshing...');
      try {
        const newToken = await CSRFService.refreshToken();
        
        // Retry request with new token
        if (options.headers) {
          (options.headers as any)['X-CSRF-Token'] = newToken;
        }
        
        return fetch(url, options);
      } catch (retryError) {
        console.error('Failed to refresh CSRF token:', retryError);
        throw retryError;
      }
    }

    return response;
  }

  private requiresCSRFToken(method: string): boolean {
    return ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method.toUpperCase());
  }

  private isCSRFError(response: Response): boolean {
    const csrfRequired = response.headers.get('X-CSRF-Required');
    const securityBlock = response.headers.get('X-Security-Block');
    return csrfRequired === 'true' || securityBlock === 'csrf-failed';
  }

  // Public API methods
  async get(endpoint: string): Promise<Response> {
    return this.makeRequest(endpoint, { method: 'GET' });
  }

  async post(endpoint: string, data: any): Promise<Response> {
    return this.makeRequest(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async put(endpoint: string, data: any): Promise<Response> {
    return this.makeRequest(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async delete(endpoint: string): Promise<Response> {
    return this.makeRequest(endpoint, { method: 'DELETE' });
  }
}

export const apiClient = new APIClient(process.env.NEXT_PUBLIC_API_URL || '');
```

### 3. React Hook for CSRF Token

Create a React hook for easy CSRF token management:

```typescript
// hooks/use-csrf-token.ts
import { useState, useEffect, useCallback } from 'react';
import CSRFService from '../lib/csrf-service';

interface UseCSRFTokenReturn {
  token: string | null;
  isLoading: boolean;
  error: string | null;
  refreshToken: () => Promise<void>;
}

export function useCSRFToken(): UseCSRFTokenReturn {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchToken = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const csrfToken = await CSRFService.getCSRFToken();
      setToken(csrfToken);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch CSRF token');
      setToken(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      setError(null);
      const csrfToken = await CSRFService.refreshToken();
      setToken(csrfToken);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh CSRF token');
    }
  }, []);

  useEffect(() => {
    fetchToken();
  }, [fetchToken]);

  return {
    token,
    isLoading,
    error,
    refreshToken,
  };
}
```

### 4. Form Integration

For forms, include CSRF token as a hidden field:

```tsx
// components/csrf-protected-form.tsx
import React from 'react';
import { useCSRFToken } from '../hooks/use-csrf-token';

interface CSRFProtectedFormProps {
  onSubmit: (formData: FormData, csrfToken: string) => Promise<void>;
  children: React.ReactNode;
}

export function CSRFProtectedForm({ onSubmit, children }: CSRFProtectedFormProps) {
  const { token: csrfToken, isLoading, error } = useCSRFToken();

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    
    if (!csrfToken) {
      console.error('CSRF token not available');
      return;
    }

    const formData = new FormData(event.currentTarget);
    formData.append('csrf_token', csrfToken);
    
    await onSubmit(formData, csrfToken);
  };

  if (isLoading) {
    return <div>Loading security token...</div>;
  }

  if (error) {
    return <div>Security error: {error}</div>;
  }

  return (
    <form onSubmit={handleSubmit}>
      <input type="hidden" name="csrf_token" value={csrfToken || ''} />
      {children}
    </form>
  );
}
```

### 5. Axios Integration (Alternative)

If using Axios instead of fetch:

```typescript
// lib/axios-csrf.ts
import axios, { AxiosRequestConfig } from 'axios';
import CSRFService from './csrf-service';

// Create axios instance
const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  withCredentials: true, // Include cookies
});

// Request interceptor to add CSRF token
apiClient.interceptors.request.use(
  async (config: AxiosRequestConfig) => {
    // Add CSRF token for state-changing requests
    if (['post', 'put', 'delete', 'patch'].includes(config.method?.toLowerCase() || '')) {
      try {
        const csrfToken = await CSRFService.getCSRFToken();
        config.headers['X-CSRF-Token'] = csrfToken;
      } catch (error) {
        console.error('Failed to get CSRF token:', error);
        throw error;
      }
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle CSRF token expiry
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 403 && error.response?.headers['x-csrf-required']) {
      try {
        // Refresh CSRF token and retry
        await CSRFService.refreshToken();
        
        // Retry original request
        const originalRequest = error.config;
        const newToken = await CSRFService.getCSRFToken();
        originalRequest.headers['X-CSRF-Token'] = newToken;
        
        return apiClient(originalRequest);
      } catch (refreshError) {
        console.error('Failed to refresh CSRF token:', refreshError);
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

## Testing CSRF Protection

### 1. Manual Testing

Test CSRF protection manually:

```bash
# 1. Get CSRF token
curl -c cookies.txt http://localhost:8000/api/v1/security/csrf-token

# 2. Extract token from response
# Token will be in both response body and Set-Cookie header

# 3. Test protected endpoint WITHOUT token (should fail)
curl -b cookies.txt -X POST http://localhost:8000/api/v1/security/test-csrf-protected

# 4. Test protected endpoint WITH token (should succeed)
curl -b cookies.txt -H "X-CSRF-Token: YOUR_TOKEN_HERE" \
     -X POST http://localhost:8000/api/v1/security/test-csrf-protected
```

### 2. Automated Testing

Run the security test suite:

```bash
cd velro-backend
python test_security_implementation.py
```

### 3. Browser Developer Tools

Check CSRF implementation in browser:
1. Open DevTools → Network tab
2. Make a state-changing request (POST/PUT/DELETE)
3. Verify request headers include `X-CSRF-Token`
4. Verify cookies include `csrf_token`
5. Check response for security headers

## Security Best Practices

### 1. Token Storage
- ✅ Store CSRF tokens in memory (not localStorage)
- ✅ Use httpOnly cookies for token storage
- ✅ Implement automatic token refresh
- ❌ Never expose tokens in URLs or logs

### 2. Request Handling
- ✅ Include `credentials: 'include'` in fetch requests
- ✅ Set `withCredentials: true` in axios
- ✅ Validate Origin/Referer headers
- ✅ Use secure, SameSite cookies

### 3. Error Handling
- ✅ Handle CSRF token expiry gracefully
- ✅ Provide user-friendly error messages
- ✅ Implement retry logic for token refresh
- ✅ Log security events for monitoring

### 4. Production Considerations
- ✅ Use HTTPS in production (required for secure cookies)
- ✅ Configure proper CORS origins
- ✅ Set secure cookie attributes
- ✅ Monitor for CSRF attacks

## Troubleshooting

### Common Issues

**1. "CSRF token required" error**
- Ensure you're calling `/api/v1/security/csrf-token` before protected requests
- Verify cookies are being sent with `credentials: 'include'`
- Check that token is included in `X-CSRF-Token` header

**2. "Invalid CSRF token" error**
- Token may have expired (2-hour limit)
- IP address may have changed
- Double-submit cookie pattern requires both header and cookie

**3. CORS issues with CSRF**
- Verify CORS origins include your frontend domain
- Ensure `credentials: 'include'` is set
- Check that preflight OPTIONS requests succeed

### Debug Endpoints

Use these endpoints for debugging:

```bash
# Get security status
GET /api/v1/security/security-status

# Get security headers info  
GET /api/v1/security/security-headers

# Validate CSRF token manually
POST /api/v1/security/validate-csrf
```

## Support

For additional support:
1. Check the security test results
2. Review server logs for CSRF-related errors
3. Verify environment configuration
4. Test with minimal reproduction case

The CSRF protection system provides enterprise-grade security while maintaining a smooth user experience when properly integrated.