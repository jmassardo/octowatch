# Audit Log Analyzer — Security & Deployment

**Version**: 1.0  
**Date**: 2026-03-25  
**Status**: Approved for Development  
**Depends on**: [docs/architecture.md](architecture.md), [docs/api-and-detection-design.md](api-and-detection-design.md)

---

## Table of Contents

1. [Security Architecture](#1-security-architecture)
   - [1.1 A01 – Broken Access Control](#11-a01--broken-access-control)
   - [1.2 A02 – Cryptographic Failures](#12-a02--cryptographic-failures)
   - [1.3 A03 – Injection](#13-a03--injection)
   - [1.4 A04 – Insecure Design](#14-a04--insecure-design)
   - [1.5 A05 – Security Misconfiguration](#15-a05--security-misconfiguration)
   - [1.6 A06 – Vulnerable and Outdated Components](#16-a06--vulnerable-and-outdated-components)
   - [1.7 A07 – Identification and Authentication Failures](#17-a07--identification-and-authentication-failures)
   - [1.8 A08 – Software and Data Integrity Failures](#18-a08--software-and-data-integrity-failures)
   - [1.9 A09 – Security Logging and Monitoring Failures](#19-a09--security-logging-and-monitoring-failures)
   - [1.10 A10 – Server-Side Request Forgery (SSRF)](#110-a10--server-side-request-forgery-ssrf)
2. [Environment Variables Reference](#2-environment-variables-reference)
3. [Health Checks and Readiness Probes](#3-health-checks-and-readiness-probes)

---

## 1. Security Architecture

This section maps every OWASP Top 10 (2021) item to concrete, code-level mitigations implemented in audit-log-analyzer. References are to the actual libraries, middleware classes, schema constructs, and configuration directives used in this stack.

---

### 1.1 A01 – Broken Access Control

**Threat:** Users access data or functions beyond their intended permissions, or horizontally pivot to another user's data.

#### Route-Level Enforcement

Every FastAPI route that reads or mutates application data declares its required role using a dependency:

```python
from app.auth.deps import require_role

@router.get("/events")
async def list_events(
    _: User = Depends(require_role(["analyst", "report_admin", "sys_admin"])),
    session: AsyncSession = Depends(get_db),
):
    ...
```

`require_role` raises `HTTP 403` before the route body executes if the resolved role (from the Valkey-validated JWT) is not in the allowed list. There is no path to a route handler without passing this dependency.

#### Org/Repo Scope Auto-Injection

Client-supplied `org` and `repo` query parameters are treated as **narrowing** filters only. The RBAC middleware resolves `scoped_orgs` and `scoped_repos` from `user_role_assignments` at request time and wraps every database query in a mandatory scope predicate:

```python
# app/db/scoping.py
def inject_scope(stmt: Select, scope: UserScope) -> Select:
    return stmt.where(
        events.c.org.in_(scope.scoped_orgs),
        or_(events.c.repo.is_(None), events.c.repo.in_(scope.scoped_repos)),
    )
```

The scope is never constructed from user-supplied values; it comes exclusively from the resolved JWT claims cross-checked against `user_role_assignments` rows in PostgreSQL.

#### Self-Service SQL — pglast CTE Rewrite

When a user submits a raw SQL query via `POST /query/sql`, the query engine:

1. Parses the submitted SQL with `pglast.parse_sql()` and verifies the parse tree contains exactly one `SELECT` statement.
2. Rejects if any `INSERT`, `UPDATE`, `DELETE`, `DROP`, `COPY`, `CALL`, `DO`, or subquery with side effects is detected.
3. Prepends a scope CTE before the user query executes:

```sql
WITH _scope AS (
    SELECT e.*
    FROM events e
    WHERE e.org = ANY(:scoped_orgs)
      AND (e.repo IS NULL OR e.repo = ANY(:scoped_repos))
),
user_query AS (
    -- original user SQL rewritten to reference _scope instead of events
    ...
)
SELECT * FROM user_query LIMIT :max_rows;
```

The CTE rewrite is performed at the AST level (not string concatenation) using `pglast`'s `RawStmt` traversal so the user cannot escape scope by aliasing or commenting.

#### Gitea Repository Permissions

Detection rules are stored in Gitea. Repository-level push permissions mirror application RBAC:

| Application Role | Gitea Permission |
|-----------------|-----------------|
| `analyst` | No access |
| `report_admin` | Read-only |
| `rule_author` | Push to feature branches; cannot merge to `main` |
| `sys_admin` | Repository admin; can merge PRs, manage branch protection |

This is enforced by Gitea's own access control, not duplicated in the application. The `GITEA_TOKEN` used by the API is a bot token with only the minimum required API scope.

#### RBAC Mutation Guarding

Modifications to `user_role_assignments` require `sys_admin`. The endpoint `PUT /admin/rbac/assignments` declares:

```python
Depends(require_role(["sys_admin"]))
```

Every successful or failed RBAC change is written to `audit_trail` with `before_state` and `after_state` as JSONB snapshots, including the actor's user ID and IP address.

---

### 1.2 A02 – Cryptographic Failures

**Threat:** Sensitive data exposed in transit or at rest due to weak or missing cryptography.

#### Secrets Management

No credentials appear in source code or committed configuration files. All secrets are injected at runtime via environment variables (see [Section 2](#2-environment-variables-reference)). The `.env.example` file committed to the repository contains only placeholder strings (`CHANGE_ME`). A pre-commit hook enforces that any file matching `*.env` or containing patterns like `password=` is blocked from commits unless whitelisted.

The following secrets must be rotated via environment variable replacement and container restart:
- `SECRET_KEY` (JWT signing key — 256-bit random, generated via `openssl rand -hex 32`)
- `POSTGRES_PASSWORD`
- `VALKEY_PASSWORD`
- `GITHUB_CLIENT_SECRET`
- `SAML_SP_KEY`
- `MINIO_ROOT_PASSWORD`
- `MINIO_INGEST_PASSWORD`
- `MAXMIND_LICENSE_KEY`

#### TLS Enforcement

All external traffic terminates TLS at Nginx. The Nginx configuration enforces:

```nginx
server {
    listen 80;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ...
}
```

TLS 1.0 and 1.1 are explicitly disabled. Internal service-to-service traffic (API → PostgreSQL, API → Valkey) uses private Docker network; PostgreSQL connections additionally require `sslmode=require` in `DATABASE_URL`.

#### JWT Design

- Algorithm: HS256 with a 256-bit random `SECRET_KEY`
- TTL: 3600 seconds (1 hour); `exp` claim validated on every request
- Storage: HTTP-only, `Secure`, `SameSite=Strict` cookie — not `localStorage`
- Revocation: every request checks `EXISTS(key=session:{jti})` in Valkey; logout deletes the key immediately

```python
# app/auth/jwt.py
def create_jwt(user_id: str, jti: str) -> str:
    payload = {
        "sub": user_id,
        "jti": jti,
        "exp": datetime.utcnow() + timedelta(seconds=settings.JWT_TTL_SECONDS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
```

#### SAML Assertion Security

`python3-saml` is configured in strict mode — both the `<Response>` and the inner `<Assertion>` must be signed. XML signature validation uses the IdP certificate pinned in `SAML_IDP_METADATA_URL` (fetched once at startup). Replay attacks are mitigated by checking `NotOnOrAfter` against server time with a maximum 5-minute clock skew tolerance.

#### Database TLS

`DATABASE_URL` must include `?sslmode=require`. The SQLAlchemy engine is created with:

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"ssl": ssl.create_default_context()},
)
```

#### MinIO Credential Scoping

MinIO service accounts follow least-privilege:

| Account | Permissions | Used by |
|---------|------------|---------|
| `MINIO_ROOT_USER` | Full admin | `minio-setup` sidecar only |
| `MINIO_INGEST_USER` | `s3:GetObject`, `s3:ListBucket` on audit bucket only | Ingestion Worker |

The ingestion worker never has access to `MINIO_ROOT_PASSWORD`. Credential separation is enforced at MinIO policy level (see `ingestion-ro` policy in `minio-setup`).

---

### 1.3 A03 – Injection

**Threat:** Untrusted data sent to an interpreter (SQL, OS, XML, etc.) as part of a command or query.

#### SQL Injection — Parameterized Queries

All database access uses SQLAlchemy Core with bound parameters. String formatting is never used to construct SQL:

```python
# CORRECT — parameterized
stmt = select(events).where(
    events.c.actor == bindparam("actor"),
    events.c.org.in_(bindparam("orgs", expanding=True)),
)
result = await session.execute(stmt, {"actor": actor_login, "orgs": scoped_orgs})

# NEVER done — string interpolation
# f"SELECT * FROM events WHERE actor = '{actor_login}'"  ← prohibited
```

The `readonly_query_user` PostgreSQL role used for self-service queries has no `INSERT`, `UPDATE`, `DELETE`, or `DDL` grants. Even a successful bypass would be limited to reads within the already-scoped CTE.

#### User-Authored SQL — pglast AST Validation

Before any user-submitted SQL query is executed, it passes through a multi-step validator:

```python
# app/query/validator.py
def validate_user_sql(sql: str) -> str:
    try:
        tree = pglast.parse_sql(sql)
    except pglast.Error as e:
        raise QueryValidationError(f"SQL parse error: {e}")

    stmts = list(tree)
    if len(stmts) != 1:
        raise QueryValidationError("Exactly one SELECT statement is required")

    stmt = stmts[0].stmt
    if not isinstance(stmt, pglast.nodes.SelectStmt):
        raise QueryValidationError("Only SELECT statements are permitted")

    _check_no_writes(stmt)       # raises if INSERT/UPDATE/DELETE/DDL found
    _check_function_allowlist(stmt)  # raises if disallowed function call found
    return _inject_scope_cte(sql, stmt)  # returns rewritten SQL
```

Allowed built-in functions are defined in an explicit allowlist (e.g., `count`, `sum`, `avg`, `min`, `max`, `date_trunc`, `extract`). Functions like `pg_read_file`, `lo_export`, `copy_to`, or any `pg_catalog` system administration function are rejected.

#### API Input Validation — Pydantic v2

All request bodies and query parameter models are declared with Pydantic v2 using strict types:

```python
class EventSearchParams(BaseModel):
    model_config = ConfigDict(strict=True)

    org: Annotated[str | None, StringConstraints(max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")] = None
    actor: Annotated[str | None, StringConstraints(max_length=255)] = None
    action: Annotated[str | None, StringConstraints(max_length=100, pattern=r"^[\w.*]+$")] = None
    page: Annotated[int, Field(ge=1, le=10000)] = 1
    page_size: Annotated[int, Field(ge=1, le=500)] = 50
```

Pydantic raises `422 Unprocessable Entity` before the route handler executes for any input that fails validation.

#### Frontend XSS Prevention

The React frontend uses React's built-in JSX escaping for all dynamic content. `dangerouslySetInnerHTML` is prohibited via ESLint rule `react/no-danger`. The Monaco Editor renders detection rule YAML as a code editor (sandboxed) — it does not interpret YAML as HTML. Apache ECharts receives typed data structures, not raw HTML strings.

#### Webhook / MinIO Event HMAC Validation

MinIO bucket event notifications arrive on the Valkey `minio:events` channel. Before the ingestion worker processes any notification, the HMAC-SHA256 signature included in the notification envelope is verified:

```python
# app/ingestion/minio_subscriber.py
def verify_event_hmac(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Events that fail HMAC validation are discarded and logged as a security event.

#### No Dynamic Code Execution

`eval()`, `exec()`, `compile()`, and `subprocess` calls with user-controlled arguments are banned via a Semgrep rule in CI (`semgrep --config p/python-security`). The detection rule DSL is interpreted by a custom evaluator that operates on a structured JSON AST — it never passes rule content to Python's interpreter.

---

### 1.4 A04 – Insecure Design

**Threat:** Design-level security flaws that cannot be fixed by correct implementation alone.

#### Threat Model

This document (Section 1) serves as the primary threat model artifact. Identified high-value attack surfaces:

| Asset | Threat | Mitigation |
|-------|--------|-----------|
| `events` table | Bulk data exfiltration via query API | Org/repo scope mandatory on all queries; 100k row cap; 30s timeout; query logged to `audit_trail` |
| Detection rules (Gitea) | Malicious rule injection to suppress detections | `rule_author` role required; PR review workflow before production promotion; full diff in `audit_trail` |
| JWT session | Token theft via XSS | HTTP-only cookie; `SameSite=Strict`; short TTL (1h); Valkey revocation |
| SAML assertion | XML signature wrapping attacks | `python3-saml` strict mode; both response and assertion must be signed; cert pinned |
| User-authored SQL | Data exfiltration beyond scope | pglast rewrite enforces scope CTE; readonly DB role; row/time limits |
| MinIO bucket | Unauthorized upload of fake events | MinIO credentials scope: ingest user has read-only; only GitHub streaming credentials have write access (configured externally by operator) |

#### Detection Rule Versioning and Promotion Workflow

Rules follow a controlled lifecycle in Gitea:

1. `rule_author` creates a feature branch and pushes YAML rule definition.
2. CI validates rule schema (Pydantic model), YAML syntax, and dry-runs the rule against a fixture dataset.
3. A PR is opened against `main`; another `rule_author` (or `sys_admin`) must approve.
4. Merge to `main` triggers the Gitea webhook → application `PUT /rules/{id}/promote` endpoint, which atomically flips `rule_definitions.is_enabled = true`.
5. Every step writes to `audit_trail` with `before_state`/`after_state`.

Rules cannot be modified in production by directly editing the database. All mutations go through the API, which re-validates via Gitea HEAD commit hash.

#### Rate Limiting

`slowapi` is applied as a FastAPI middleware:

| Endpoint Group | Limit | Scope |
|---------------|-------|-------|
| `/auth/*` | 10 req/min | Per client IP |
| `POST /query/sql` | 5 concurrent, 30s timeout | Per authenticated user |
| Read endpoints (`GET /events`, `GET /detections`) | 60 req/min | Per authenticated user |
| Write endpoints (`POST /rules`, `PUT /rules/*`) | 10 req/min | Per authenticated user |
| Row result cap | 100,000 rows | Per query |

#### Database Principle of Least Privilege

Four PostgreSQL roles exist, each with minimal grants:

| Role | Grants | Used by |
|------|--------|---------|
| `migration_user` | Superuser during migration only; removed after | `alembic upgrade head` |
| `app_rw` | `INSERT`, `UPDATE`, `SELECT` on application tables | API, Celery workers |
| `app_ro` | `SELECT` on application tables | Internal read-only paths |
| `readonly_query_user` | `SELECT` on `events`, `detections` only; no system tables | Self-service query engine |

`app_rw` cannot `DROP` tables. `readonly_query_user` cannot see `user_role_assignments`, `audit_trail`, or any secrets.

---

### 1.5 A05 – Security Misconfiguration

**Threat:** Insecure default configurations, unnecessary features enabled, missing hardening.

#### Container Hardening

All Docker images are built `FROM python:3.12-slim`. No additional OS packages are installed unless strictly required. All containers run as a non-root user:

```dockerfile
# Dockerfile.api
FROM python:3.12-slim
RUN useradd -r -u 1001 -g root appuser
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Gitea uses the official `gitea/gitea:1.22-rootless` image (pre-configured for non-root).

#### Kubernetes / Helm Security Context

`helm/values.yaml` sets the following defaults (see [helm/values.yaml](../helm/values.yaml)):

```yaml
securityContext:
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  runAsNonRoot: true
  runAsUser: 1001
  capabilities:
    drop: ["ALL"]
```

These are enforced at the Pod spec level and cannot be overridden without `sys_admin` cluster access.

#### HTTP Security Headers

The Nginx configuration sets the following response headers on all responses:

```nginx
# Prevent MIME-type sniffing
add_header X-Content-Type-Options "nosniff" always;

# Do not render in frames (clickjacking prevention)
add_header X-Frame-Options "DENY" always;

# HSTS — 2-year max-age, includeSubDomains, preload
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

# Content Security Policy — restrict execution contexts
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';" always;

# Referrer policy
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Permissions policy
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

# Disable server version disclosure
server_tokens off;
```

The `style-src 'self' 'unsafe-inline'` exception is required for TailwindCSS's runtime-injected styles and will be narrowed to a nonce once the build pipeline supports CSP nonces.

#### MinIO Bucket Policy

MinIO is configured with a private bucket policy (no public read). The CORS policy restricts preflight requests to the application origin only:

```json
{
  "CORSConfiguration": {
    "CORSRule": [{
      "AllowedOrigins": ["https://YOUR_APP_DOMAIN"],
      "AllowedHeaders": ["Authorization", "Content-Type"],
      "AllowedMethods": ["GET", "PUT"],
      "MaxAgeSeconds": 3000
    }]
  }
}
```

The MinIO console port (9001) is exposed only on `127.0.0.1` and is never proxied through Nginx.

---

### 1.6 A06 – Vulnerable and Outdated Components

**Threat:** Components with known vulnerabilities used in production.

#### Automated Dependency Scanning

The following automated checks run in the CI pipeline on every pull request:

| Tool | Scope | Failure behavior |
|------|-------|-----------------|
| `pip-audit` | Python dependencies (pip) | PR blocked on `CRITICAL` or `HIGH` CVEs |
| `npm audit --audit-level=high` | JavaScript dependencies (npm) | PR blocked on `HIGH`+ CVEs |
| `trivy image` | Docker image layers | PR blocked on `CRITICAL` CVEs |
| `semgrep --config p/python-security` | Static analysis — Python | PR blocked on any finding |
| `semgrep --config p/react` | Static analysis — React/TypeScript | PR blocked on any finding |

Dependabot is enabled for all three ecosystems (`pip`, `npm`, `docker`) with weekly update PRs.

#### License Compliance

Because MinIO (AGPL-3.0) and pglast (GPL-3.0) are included as infrastructure components (not bundled into distributed binaries), their copyleft licenses are acceptable for self-hosted deployment. This is documented and gated in CI via:

```bash
# Run in CI on every dependency update PR
pip-licenses --order=license --fail-on="GPL-2.0;LGPL-2.0"
npx license-checker --failOn "GPL-2.0;LGPL-2.0"
```

AGPL components (MinIO) are listed in `NOTICE.md` with the required attribution.

#### Image Pinning

All Docker images in `docker-compose.yml` and Helm chart are pinned to exact version tags or digest SHAs. `minio/mc:latest` is the only exception (used in the one-time `minio-setup` sidecar) and is noted in comments.

---

### 1.7 A07 – Identification and Authentication Failures

**Threat:** Broken authentication mechanisms, credential exposure, session management failures.

#### Session Architecture

Sessions are implemented as a two-token pattern:

1. **JWT** — contains `sub` (user ID), `jti` (session UUID), `exp`, `iat`. Signed HS256. Stored in HTTP-only `Secure` `SameSite=Strict` cookie.
2. **Valkey session key** — `session:{jti}` key with TTL=3600. Checked via `EXISTS` on every authenticated request.

This design enables instant revocation: the logout endpoint calls `DEL session:{jti}`, after which the JWT is treated as invalid even if it has not expired.

```python
# app/auth/middleware.py
async def get_current_user(
    request: Request, valkey: Valkey = Depends(get_valkey)
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    jti = payload.get("jti")
    if not await valkey.exists(f"session:{jti}"):
        raise HTTPException(status_code=401, detail="Session revoked")

    return await load_user(payload["sub"])
```

#### No Password Storage

The application has no local password store. Authentication is GitHub OAuth or SAML 2.0 only. There is no `passwords` table and no password-reset flow — these attack surfaces do not exist.

#### CSRF Protection — Double-Submit Cookie

For state-changing API requests (any non-GET method), the Double-Submit Cookie pattern is used alongside `SameSite=Strict`:

1. At session creation, a random 256-bit `csrf_token` is written to a non-HTTP-only cookie `csrf_token` (readable by JavaScript) and stored in the JWT payload.
2. Every mutating request must include an `X-CSRF-Token` header matching the `csrf_token` claim in the JWT.
3. The CSRF middleware validates the match before the route handler runs.

`SameSite=Strict` is treated as defense-in-depth only — the Double-Submit Cookie pattern does not rely on it.

#### OAuth State Parameter

During the GitHub OAuth flow, a cryptographically random `state` parameter is generated and stored in a signed cookie:

```python
state = secrets.token_urlsafe(32)
response.set_cookie("oauth_state", state, httponly=True, secure=True, samesite="strict", max_age=600)
redirect_uri = f"https://github.com/login/oauth/authorize?client_id={client_id}&state={state}&scope=read:org"
```

The callback handler verifies the returned `state` matches the cookie value before exchanging the authorization code.

#### SAML Replay Prevention

`python3-saml` is configured to check `NotOnOrAfter` with a 5-minute clock tolerance (`SECURITY_REJECT_DEPRECATED_ALGORITHM=True`). The `InResponseTo` attribute is validated against the pending authentication request ID stored in the session. Used assertion IDs are cached in Valkey (TTL = assertion validity window) to detect replays.

---

### 1.8 A08 – Software and Data Integrity Failures

**Threat:** Unsigned code updates, deserialization of untrusted data, CI/CD pipeline compromises.

#### GitHub Actions — Pinned Action SHAs

All workflow steps use commit SHA pinning, not mutable version tags:

```yaml
# .github/workflows/ci.yml — correct pattern
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
- uses: docker/build-push-action@48aba3b46d1b1fde0e46c1f98b4a5fef5e8e3a1e  # v6.6.0

# NEVER:
# - uses: actions/checkout@v4  ← mutable tag, susceptible to tag hijack
```

#### Docker Image Attestation

Docker images are built with SBOM generation and signed using `docker/build-push-action`:

```yaml
- uses: docker/build-push-action@...
  with:
    provenance: true
    sbom: true
    push: true
    tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ env.VERSION }}
```

The SBOM (SPDX format) is uploaded to the container registry as an attestation and is verifiable with `docker buildx imagetools inspect`.

#### Alembic Migration Integrity

Database migrations are managed by Alembic. Each migration file is checksummed: `alembic upgrade head` verifies that the down_revision and `rev_id` chain is unbroken before applying. Migration files are committed to the repository and cannot be modified after merging (enforced by branch protection and the Alembic checksum chain).

#### MinIO Event HMAC

Bucket event notification payloads from `minio:events` Valkey channel are HMAC-SHA256 validated before processing (see also [Section 1.3 – Injection](#13-a03--injection)).

---

### 1.9 A09 – Security Logging and Monitoring Failures

**Threat:** Insufficient logging of security events; inability to detect active attacks or investigate incidents.

#### audit_trail Table

Every state-changing operation writes a row to `audit_trail`. The audit trail middleware intercepts mutating HTTP methods only (`POST`, `PUT`, `PATCH`, `DELETE`) and records an entry only when an authenticated actor can be extracted from the JWT session cookie. Read-only requests (`GET`, `HEAD`, `OPTIONS`) are not recorded in the audit trail — they are captured by the separate request logging middleware instead.

```sql
CREATE TABLE audit_trail (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      UUID          NOT NULL REFERENCES users(id),
    action       TEXT          NOT NULL,  -- e.g. "rule.create", "rbac.assign"
    resource_type TEXT         NOT NULL,
    resource_id  TEXT,
    before_state JSONB,                   -- full snapshot of previous state
    after_state  JSONB,                   -- full snapshot of new state
    ip_address   INET          NOT NULL,
    user_agent   TEXT,
    timestamp    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
```

`before_state` and `after_state` store full JSONB snapshots so investigators can reconstruct what changed without a separate diff tool.

> **Clarification:** The audit trail middleware only logs mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`), and only when an authenticated actor can be extracted from the JWT cookie. Read-only `GET`/`HEAD`/`OPTIONS` requests are handled by the separate request logging middleware and are not written to the `audit_trail` table.

#### Logged Security Events

| Event | Log destination | Severity |
|-------|----------------|----------|
| Login success (OAuth / SAML) | `audit_trail` + structured log | INFO |
| Login failure (invalid OAuth state / SAML validation failed) | `audit_trail` + structured log | WARNING |
| Logout | `audit_trail` | INFO |
| JWT expired or revoked | Structured log | INFO |
| CSRF token mismatch | Structured log | WARNING |
| RBAC role change | `audit_trail` (before/after state) | WARNING |
| Forbidden access attempt (403) | `audit_trail` + structured log | WARNING |
| Detection rule create/update/delete | `audit_trail` + Gitea commit | INFO |
| SAML assertion received | Structured log (no PII in payload) | DEBUG |
| pglast SQL validation rejection | Structured log | WARNING |
| MinIO HMAC validation failure | Structured log | ERROR |

#### Request Logging Middleware

Every request is logged as structured JSON (via `structlog`):

```python
# app/middleware/logging.py
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    structlog.get_logger().info(
        "http.request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
        client_ip=request.client.host,
        user_id=getattr(request.state, "user_id", None),
        request_id=request.headers.get("X-Request-ID"),
    )
    return response
```

Log level is controlled by the `LOG_LEVEL` environment variable (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

#### Alert Deduplication Without Suppression Gaps

Valkey stores dedup keys per detection alert with a short TTL (configurable; default 5 minutes). This prevents alert fatigue from duplicated events while guaranteeing at-least-one notification per detection firing. The dedup key format is `alert:dedup:{rule_id}:{actor}:{org}:{bucket}` where `bucket` is a time-bucketed window.

---

### 1.10 A10 – Server-Side Request Forgery (SSRF)

**Threat:** The application is tricked into making server-side HTTP requests to internal resources on behalf of an attacker.

#### Outbound HTTP Allowlist

No outbound HTTP requests are made to user-supplied URLs. Operator-configured external endpoints (IdP, notification targets, ticketing systems) are validated against an allowlist at application startup:

```python
# app/config.py
ALLOWED_IDP_HOSTS: set[str] = {
    urlparse(settings.OKTA_ORG_URL).hostname,
    "login.microsoftonline.com",
    "graph.microsoft.com",
    "accounts.google.com",
    "www.googleapis.com",
}

def validate_outbound_url(url: str, context: str) -> None:
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_OUTBOUND_HOSTS:
        raise ConfigurationError(f"SSRF protection: {context} URL host '{parsed.hostname}' not in allowlist")
```

This validation runs at startup — a misconfigured or injected URL causes the process to exit immediately rather than silently enabling SSRF.

#### No User-Controlled URL Construction

Webhook URLs for Slack notifications, ticketing system endpoints, and IdP base URLs are sourced exclusively from environment variables. No code path constructs an outbound URL from user-supplied request data. This is verified by the Semgrep rule `app.security.no-user-url-construction`.

#### S3/Azure Blob Connection Validation

When `INGESTION_MODE=s3`, the `AWS_DEFAULT_REGION` and `S3_AUDIT_BUCKET` are validated against a regex pattern at ingestion config load time (`^[a-z0-9-]+$` for region; `^[a-z0-9-\.]{3,63}$` for bucket name). The S3 endpoint is always `https://s3.{region}.amazonaws.com` — never a user-supplied URL.

When `INGESTION_MODE=azure_blob`, the `AZURE_STORAGE_CONNECTION_STRING` is parsed and the account endpoint hostname is validated against `*.blob.core.windows.net`.

#### MinIO Internal Addressing

The `MINIO_ENDPOINT_URL` for internal service communication defaults to `http://minio:9000` (Docker Compose internal network) and is validated at startup to be either the internal Docker network address or an operator-configured private hostname. It is never derived from request parameters.

---

## 2. Environment Variables Reference

Variables are grouped by subsystem, then sorted alphabetically within each group. Variables marked **Required** must be set; the application will fail at startup if they are absent.

### 2.1 Core Application

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `DATABASE_URL` | api, all workers | Yes | — | PostgreSQL connection string. Format: `postgresql+asyncpg://user:pass@host:5432/dbname?sslmode=require` |
| `DETECTION_CONFIDENCE_THRESHOLD` | worker-detection | No | `0.7` | Minimum confidence score (0.0–1.0) for a detection to be persisted and trigger notifications |
| `GEOIP_DB_PATH` | api, worker-ingestion | No | `/app/data/GeoLite2-City.mmdb` | Filesystem path to the MaxMind GeoLite2 City `.mmdb` file |
| `GITEA_TOKEN` | api | Yes | — | Gitea bot account access token with `repo` scope for rule CRUD operations |
| `GITEA_URL` | api | Yes | — | Base URL of the embedded Gitea instance. Example: `http://gitea:3000` |
| `INGESTION_MODE` | api, worker-ingestion | No | `minio` | Active ingestion backend: `minio`, `s3`, or `azure_blob` |
| `LOG_LEVEL` | api, all workers | No | `INFO` | Structured log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `QUERY_MAX_ROWS` | api | No | `100000` | Maximum rows returned by the self-service SQL query engine per execution |
| `QUERY_TIMEOUT_SECONDS` | api | No | `30` | Server-side timeout for self-service SQL queries |
| `SECRET_KEY` | api | Yes | — | HS256 JWT signing key. Must be a 256-bit (32-byte) random hex string. Generate with: `openssl rand -hex 32` |
| `VALKEY_URL` | api, all workers | Yes | — | Valkey connection string. Format: `redis://:password@valkey:6379/0` |

### 2.2 Authentication — GitHub OAuth

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `GITHUB_CLIENT_ID` | api | Yes | — | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | api | Yes | — | GitHub OAuth App client secret |

### 2.3 Authentication — SAML 2.0

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `SAML_IDP_METADATA_URL` | api | No | — | URL of the IdP SAML metadata XML. Required if SAML authentication is enabled. Example: `https://your-idp.example.com/metadata.xml` |
| `SAML_SP_CERT` | api | No | — | PEM-encoded SP certificate (public key). Required if SAML is enabled |
| `SAML_SP_KEY` | api | No | — | PEM-encoded SP private key. Required if SAML is enabled. Never commit to git |

### 2.4 Storage — MinIO (Embedded)

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `MINIO_AUDIT_BUCKET` | minio, minio-setup, api, worker-ingestion | Yes | — | Name of the MinIO bucket storing GitHub audit log `.json.gz` files |
| `MINIO_ENDPOINT_URL` | api, worker-ingestion | No | `http://minio:9000` | Internal MinIO S3-compatible API endpoint |
| `MINIO_INGEST_PASSWORD` | minio-setup, worker-ingestion | Yes | — | Password for the scoped MinIO service account with read-only access to the audit bucket |
| `MINIO_INGEST_USER` | minio-setup, worker-ingestion | Yes | — | Username for the scoped MinIO service account with read-only access to the audit bucket |
| `MINIO_ROOT_PASSWORD` | minio, minio-setup | Yes | — | MinIO admin password. Never used by application workers |
| `MINIO_ROOT_USER` | minio, minio-setup | Yes | — | MinIO admin username. Never used by application workers |

### 2.5 Storage — AWS S3

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | worker-ingestion | Conditional | — | AWS IAM access key ID. Required when `INGESTION_MODE=s3` |
| `AWS_DEFAULT_REGION` | worker-ingestion | Conditional | — | AWS region of the S3 bucket. Required when `INGESTION_MODE=s3`. Example: `us-east-1` |
| `AWS_SECRET_ACCESS_KEY` | worker-ingestion | Conditional | — | AWS IAM secret access key. Required when `INGESTION_MODE=s3` |
| `S3_AUDIT_BUCKET` | worker-ingestion | Conditional | — | Name of the AWS S3 bucket storing GitHub audit logs. Required when `INGESTION_MODE=s3` |

### 2.6 Storage — Azure Blob

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `AZURE_AUDIT_CONTAINER` | worker-ingestion | Conditional | — | Azure Blob container name. Required when `INGESTION_MODE=azure_blob` |
| `AZURE_STORAGE_CONNECTION_STRING` | worker-ingestion | Conditional | — | Azure Storage connection string. Required when `INGESTION_MODE=azure_blob`. Hostname validated to `*.blob.core.windows.net` |

### 2.7 GeoIP

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `MAXMIND_LICENSE_KEY` | worker-ingestion (init) | No | — | MaxMind account license key used to download the GeoLite2 City database at container startup. If absent, GeoIP enrichment is skipped |

### 2.8 IdP Enrichment — Okta

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `OKTA_API_TOKEN` | worker-detection | No | — | Okta API token for actor enrichment lookups. Required if Okta enrichment is enabled |
| `OKTA_ORG_URL` | worker-detection | No | — | Okta Org base URL. Example: `https://your-org.okta.com`. Validated against allowlist at startup |

### 2.9 IdP Enrichment — Azure AD / Entra

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `AZURE_AD_CLIENT_ID` | worker-detection | No | — | Azure AD application (client) ID for Entra enrichment |
| `AZURE_AD_CLIENT_SECRET` | worker-detection | No | — | Azure AD client secret |
| `AZURE_AD_TENANT_ID` | worker-detection | No | — | Azure AD tenant ID |

### 2.10 IdP Enrichment — Google Workspace

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | worker-detection | No | — | JSON content of the Google service account key file with `Directory API` read scope |
| `GOOGLE_WORKSPACE_DOMAIN` | worker-detection | No | — | Primary Google Workspace domain. Example: `example.com` |

### 2.11 Ticketing Integrations

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `JIRA_API_TOKEN` | worker-detection | No | — | Jira user API token (Atlassian account token, not OAuth) |
| `JIRA_URL` | worker-detection | No | — | Jira instance base URL. Example: `https://your-org.atlassian.net` |
| `JIRA_USERNAME` | worker-detection | No | — | Jira account email address associated with `JIRA_API_TOKEN` |

### 2.12 Notifications — Slack

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | worker-detection | No | — | Slack Bot OAuth token (`xoxb-...`) with `chat:write` scope |

### 2.13 Notifications — Email (SMTP)

| Variable | Service(s) | Required | Default | Description |
|----------|------------|----------|---------|-------------|
| `SMTP_FROM_ADDRESS` | worker-detection | No | — | From address for outbound alert email. Example: `alerts@example.com` |
| `SMTP_HOST` | worker-detection | No | — | SMTP server hostname. Example: `smtp.sendgrid.net` |
| `SMTP_PASSWORD` | worker-detection | No | — | SMTP authentication password or API key |
| `SMTP_PORT` | worker-detection | No | `587` | SMTP server port. Use `587` for STARTTLS or `465` for implicit TLS |
| `SMTP_USERNAME` | worker-detection | No | — | SMTP authentication username |

---

## 3. Health Checks and Readiness Probes

This section defines health check commands for Docker Compose and the equivalent Kubernetes liveness, readiness, and startup probe specifications for Helm deployments.

### 3.1 Probe Summary Table

| Service | Liveness Probe | Readiness Probe | Startup Probe |
|---------|---------------|-----------------|---------------|
| `api` | `GET /health` — returns 200 if process is alive | `GET /ready` — returns 200 only when DB connection pool and Valkey are responsive | `GET /health` — `failureThreshold: 30`, `periodSeconds: 10` (allows 5 min for startup) |
| `worker-ingestion` | `celery inspect ping -d celery@$HOSTNAME` | `celery inspect ping -d celery@$HOSTNAME` | None — Celery workers register via Valkey on first task |
| `worker-detection` | `celery inspect ping -d celery@$HOSTNAME` | `celery inspect ping -d celery@$HOSTNAME` | None |
| `worker-baseline` | `celery inspect ping -d celery@$HOSTNAME` | `celery inspect ping -d celery@$HOSTNAME` | None |
| `db` | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB` | `pg_isready` — `failureThreshold: 6`, `periodSeconds: 10` (allows 1 min for first boot) |
| `valkey` | `valkey-cli -a $VALKEY_PASSWORD ping` | `valkey-cli -a $VALKEY_PASSWORD ping` | None |
| `minio` | `curl -f http://localhost:9000/minio/health/live` — process alive | `curl -f http://localhost:9000/minio/health/cluster` — fully initialized and erasure set healthy | `curl -f http://localhost:9000/minio/health/live` — `failureThreshold: 10`, `periodSeconds: 10` |
| `gitea` | `curl -f http://localhost:3000/api/healthz` | `curl -f http://localhost:3000/api/healthz` — database connection verified by Gitea | `curl -f http://localhost:3000/api/healthz` — `failureThreshold: 30`, `periodSeconds: 10` (allows 5 min for db migration on first boot) |

### 3.2 API `/health` vs `/ready` Contract

**`GET /health`** — Liveness only. Returns `200 OK` immediately if the Python process is running. Does not check dependencies. Used by the container runtime to decide whether to restart the container.

```json
{ "status": "ok", "version": "1.0.0" }
```

**`GET /ready`** — Readiness. Performs active connectivity checks before returning `200`. Returns `503 Service Unavailable` if any dependency is unreachable. Used by the load balancer to stop routing traffic to a starting or degraded instance.

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "valkey": "ok",
    "geoip_db": "ok"
  }
}
```

If `database` returns `error`, the response is HTTP 503:

```json
{
  "status": "not_ready",
  "checks": {
    "database": "error: connection refused",
    "valkey": "ok",
    "geoip_db": "ok"
  }
}
```

### 3.3 Kubernetes Probe Specifications

The following Kubernetes probe specs are used in the Helm chart (`helm/templates/`):

**API deployment:**

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
  timeoutSeconds: 10
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /health
    port: 8000
  failureThreshold: 30
  periodSeconds: 10
  timeoutSeconds: 5
```

**Celery Workers (ingestion, detection, baseline):**

```yaml
livenessProbe:
  exec:
    command:
      - celery
      - inspect
      - ping
      - -d
      - celery@$(HOSTNAME)
      - --timeout
      - "10"
  initialDelaySeconds: 30
  periodSeconds: 60
  timeoutSeconds: 15
  failureThreshold: 3

readinessProbe:
  exec:
    command:
      - celery
      - inspect
      - ping
      - -d
      - celery@$(HOSTNAME)
      - --timeout
      - "10"
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 15
  failureThreshold: 3
```

**PostgreSQL (db):**

```yaml
livenessProbe:
  exec:
    command:
      - pg_isready
      - -U
      - $(POSTGRES_USER)
      - -d
      - $(POSTGRES_DB)
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6

readinessProbe:
  exec:
    command:
      - pg_isready
      - -U
      - $(POSTGRES_USER)
      - -d
      - $(POSTGRES_DB)
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

startupProbe:
  exec:
    command:
      - pg_isready
      - -U
      - $(POSTGRES_USER)
      - -d
      - $(POSTGRES_DB)
  failureThreshold: 6
  periodSeconds: 10
  timeoutSeconds: 5
```

**Valkey:**

```yaml
livenessProbe:
  exec:
    command:
      - valkey-cli
      - -a
      - $(VALKEY_PASSWORD)
      - ping
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  exec:
    command:
      - valkey-cli
      - -a
      - $(VALKEY_PASSWORD)
      - ping
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

**MinIO:**

```yaml
livenessProbe:
  httpGet:
    path: /minio/health/live
    port: 9000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 20
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /minio/health/cluster
    port: 9000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 20
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /minio/health/live
    port: 9000
  failureThreshold: 10
  periodSeconds: 10
  timeoutSeconds: 20
```

**Gitea:**

```yaml
livenessProbe:
  httpGet:
    path: /api/healthz
    port: 3000
  initialDelaySeconds: 20
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 5

readinessProbe:
  httpGet:
    path: /api/healthz
    port: 3000
  initialDelaySeconds: 20
  periodSeconds: 15
  timeoutSeconds: 10
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /api/healthz
    port: 3000
  failureThreshold: 30
  periodSeconds: 10
  timeoutSeconds: 10
```
