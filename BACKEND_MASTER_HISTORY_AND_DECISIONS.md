# Backend Master: History and Decisions

## Overview
- Service: `velro-backend` (FastAPI, Python 3.11) deployed independently on Railway.
- Auth: Supabase JWT; default new signup credits: 1000 (`DEFAULT_USER_CREDITS`).
- Generation: FAL.ai async queue, Redis-backed caching/status; async endpoints under `/api/v1/generations/async/*`.

## Key Incidents & Fixes
- Auth middleware mismatch caused `'bool' object has no attribute get'` errors. Aligned middleware with Supabase auth service and/or returned Dict from async auth path; added missing `get_authenticated_client`.
- Public endpoints (e.g., `/api/v1/generations/models/supported`) whitelisted to allow unauthenticated access.
- Parameter filtering added to prevent 422 errors from model-specific params.
- Redis internal DNS corrected (`redis://...railway.internal:6379`).

## Architecture Decisions
- Direct Frontend → Backend communication (Kong not in main path).
- Use `fal_client.submit_async()` with status polling/SSE instead of blocking `run()`.
- Cache results in Redis; plan CDN persistence to avoid expiring FAL URLs.
- Reserve/deduct credits in transactional manner in Supabase with rollback handling.

## Current State
- Async endpoints live; Redis required for completion/status.
- Auth flow stable; tokens validated; public endpoints configured.
- Monitoring endpoints exposed (health and async system metrics).

## Risks
- Redis availability is a hard dependency; document failover/backpressure.
- Ensure rate limit policies and CORS origins remain explicit and enforced.

## Next Steps
- Enforce JWT signature and expiry validation uniformly.
- Implement CDN persistence pipeline for generated assets.
- CI coverage thresholds; routine audits.

## Async API
- POST `/api/v1/generations/async/submit`
- GET `/api/v1/generations/async/{id}/status`
- GET `/api/v1/generations/async/{id}/stream`
- DELETE `/api/v1/generations/async/{id}/cancel`
- GET `/api/v1/generations/models/supported`


