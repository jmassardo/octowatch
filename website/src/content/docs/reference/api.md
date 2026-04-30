---
title: API Reference
description: OctoWatch REST API documentation
---

# API Reference

OctoWatch exposes a REST API built with FastAPI. The API serves both the web frontend and programmatic integrations.

## Interactive Documentation

OctoWatch includes auto-generated interactive API documentation:

- **Swagger UI**: `https://your-domain/docs`
- **ReDoc**: `https://your-domain/redoc`
- **OpenAPI spec**: `https://your-domain/openapi.json`

These are the authoritative API references and stay in sync with the deployed version.

## Authentication

All API requests (except `/health` and auth endpoints) require authentication:

```http
GET /api/v1/events HTTP/1.1
Host: octowatch.yourdomain.com
Cookie: session=<jwt-token>
```

Or via Bearer token for programmatic access:

```http
GET /api/v1/events HTTP/1.1
Host: octowatch.yourdomain.com
Authorization: Bearer <api-token>
```

## Key Endpoints

### Health Check

```http
GET /health
```

Returns system health status. No authentication required.

### Events

```http
GET /api/v1/events
GET /api/v1/events/{event_id}
```

Query audit log events with filtering, sorting, and pagination.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `org` | string | Filter by organization |
| `actor` | string | Filter by actor (GitHub username) |
| `action` | string | Filter by action type |
| `since` | datetime | Events after this timestamp |
| `until` | datetime | Events before this timestamp |
| `page` | int | Page number (default: 1) |
| `per_page` | int | Items per page (default: 50, max: 100) |

### Organizations

```http
GET /api/v1/organizations
POST /api/v1/organizations
GET /api/v1/organizations/{org_id}
POST /api/v1/organizations/{org_id}/sync
```

Manage monitored organizations and trigger syncs.

### Reports

```http
GET /api/v1/reports
POST /api/v1/reports/generate
GET /api/v1/reports/{report_id}
GET /api/v1/reports/{report_id}/download
```

Generate and retrieve compliance reports.

### Detection Rules

```http
GET /api/v1/detection-rules
POST /api/v1/detection-rules
PUT /api/v1/detection-rules/{rule_id}
DELETE /api/v1/detection-rules/{rule_id}
GET /api/v1/detection-rules/{rule_id}/alerts
```

Manage detection rules and view triggered alerts.

### Users & RBAC

```http
GET /api/v1/users
POST /api/v1/users
PUT /api/v1/users/{user_id}/role
DELETE /api/v1/users/{user_id}
```

User management and role assignment (requires `sys_admin` or `org_admin`).

## Rate Limiting

API requests are rate-limited:

| Endpoint Group | Limit |
|---------------|-------|
| Standard API | 60 requests/minute |
| Reports | 10 requests/minute |
| HEC Ingest | 100 requests/second |

Rate limit headers are included in responses:

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1700000000
```

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Human-readable error message",
  "status_code": 403,
  "error_type": "permission_denied"
}
```

| Status Code | Meaning |
|------------|---------|
| 400 | Invalid request parameters |
| 401 | Authentication required |
| 403 | Insufficient permissions (RBAC) |
| 404 | Resource not found |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
