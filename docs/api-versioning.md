# API Versioning

## Current Version

The OctoWatch API is currently at **v1**, accessible at `/api/v1/`.

## Versioning Strategy

OctoWatch uses **URL path prefix versioning** (e.g., `/api/v1/`, `/api/v2/`). This approach provides:

- Clear, explicit version identification in every request
- Easy routing at the reverse proxy layer
- Simple client configuration

## Backwards Compatibility

Within a major API version:

- **No breaking changes** to existing endpoint request/response schemas
- New optional fields may be added to responses
- New optional query parameters may be added to requests
- New endpoints may be added

## Deprecation Policy

When a new API version is released:

1. The previous version will be supported for a minimum of **6 months**
2. Deprecation warnings will be communicated via:
   - `Sunset` and `Deprecation` HTTP headers on deprecated endpoints
   - Release notes and changelog entries
   - Documentation updates
3. After the deprecation period, the old version may be removed

## Version History

| Version | Status | Released   | Sunset |
|---------|--------|------------|--------|
| v1      | Active | 2026-03-27 | —      |
