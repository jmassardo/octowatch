# ADR-001: Replace MinIO with Splunk HEC Ingestion

| Field      | Value                        |
|------------|------------------------------|
| **Status** | Accepted                     |
| **Date**   | 2026-04-15                   |
| **Author** | Platform Team                |

---

## Context

OctoWatch originally used an embedded [MinIO](https://min.io/) object store as
the primary ingestion buffer for GitHub Enterprise audit log events. GitHub would
stream `.json.gz` audit log files to a MinIO bucket; the ingestion worker would
poll the bucket, decompress files, parse events, and write them to TimescaleDB.

### Why MinIO was removed

MinIO's license changed from Apache 2.0 to AGPL-3.0 in early 2021, and the
project subsequently reached end-of-life for the embedded single-node
configuration. The specific upstream commit that removed support for the
single-node mode OctoWatch relied on is:

> `https://github.com/minio/minio/commit/7aac2a2c5b7c882e68c1ce017d8256be2feea27f`

In addition to the EOL status, operating MinIO in production introduced
significant operational overhead:

- A dedicated `minio-setup` sidecar was required to bootstrap bucket policies
  and scoped service accounts on every deployment.
- Two additional secrets (`MINIO_ROOT_PASSWORD`, `MINIO_INGEST_PASSWORD`) had
  to be rotated independently.
- Disk I/O provisioning for the `minio_data` volume added cost and complexity.
- Erasure-set health checks (`/minio/health/cluster`) were a frequent source of
  false-positive readiness failures in Kubernetes.

### GitHub's native audit log streaming support

GitHub Enterprise Cloud and GitHub Enterprise Server (≥ 3.8) now support
pushing audit log events directly to a
[Splunk HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data/UsetheHTTPEventCollector)
compatible endpoint. This eliminates the need for an intermediate object store:
GitHub becomes the push origin, and OctoWatch becomes the receiver.

---

## Decision

Replace the MinIO ingestion backend with a Splunk HEC-compatible receiver
built directly into the OctoWatch API service.

### HEC endpoint

| Property | Value |
|----------|-------|
| Path | `POST /services/collector` |
| Also accepts | `POST /services/collector/event`, `POST /services/collector/event/1.0` |
| Health check | `GET /services/collector/health` → `{"text": "HEC is healthy", "code": 17}` |
| Auth | `Authorization: Splunk <HEC_TOKEN>` header |
| Token validation | `hmac.compare_digest` (constant-time, immune to timing attacks) |
| Payload formats | Single JSON object, NDJSON, concatenated JSON (`{}{}`) |

The path `/services/collector` matches what GitHub sends to a Splunk HEC
endpoint verbatim — no path remapping is needed in GitHub's audit log stream
configuration.

### Ingestion mode changes

| Old value | New value | Type | Notes |
|-----------|-----------|------|-------|
| `minio` (default) | _(removed)_ | push | Replaced by HEC |
| — | `hec` (new default) | push | GitHub streams directly to OctoWatch |
| — | `webhook` (new) | push | Generic webhook receiver |
| `s3` | `s3` | poll | Unchanged — Celery Beat polling |
| `azure_blob` | `azure_blob` | poll | Unchanged — Celery Beat polling |

The `INGESTION_MODE` environment variable default changes from `minio` to `hec`.

### What was removed

- MinIO service and `minio-setup` sidecar from `docker-compose.yml` and Helm chart
- `MINIO_*` environment variables (6 variables eliminated)
- `minio_data` Docker volume and Helm PersistentVolumeClaim
- `app/workers/ingestion/minio_worker.py` (and associated tests)
- MinIO health check probes from Kubernetes manifests
- MinIO bucket CORS policy configuration

### What was added

- `app/routers/ingest_hec.py` — FastAPI router implementing the HEC receiver
- `app/routers/ingest_webhook.py` — Generic webhook receiver
- `app/workers/ingestion/base.py` — Abstract base for poll-based ingestion workers
- `app/workers/ingestion/s3_worker.py` — Refactored S3 worker using the base class
- `app/workers/ingestion/azure_worker.py` — Refactored Azure worker using the base class
- `HEC_TOKEN` environment variable (single secret replaces six MinIO credentials)

---

## Consequences

### Positive

- **Simpler operations**: One service fewer to operate. No bucket policies,
  no service account bootstrap, no erasure-set health monitoring.
- **Fewer secrets**: Six `MINIO_*` variables replaced by a single `HEC_TOKEN`.
- **Lower latency**: Events arrive within seconds of being generated rather than
  after the file-polling interval.
- **License clarity**: AGPL-3.0 dependency removed from the stack. OctoWatch
  now has no copyleft infrastructure components.
- **Standards alignment**: The HEC protocol is widely supported — operators who
  already run Splunk can point their existing HEC forwarder at OctoWatch or run
  both simultaneously.

### Negative / Trade-offs

- **Push vs. pull durability**: If OctoWatch is unreachable when GitHub attempts
  delivery, events are lost (GitHub retries for a limited window). Operators who
  need guaranteed delivery should configure `INGESTION_MODE=s3` or
  `INGESTION_MODE=azure_blob` as a secondary sink.
- **IP allowlisting required**: Operators must configure their firewall to allow
  GitHub's published IP ranges to reach the `/services/collector` endpoint.
  GitHub's current IP ranges are available at `https://api.github.com/meta`.
- **HEC_TOKEN rotation requires GitHub reconfiguration**: Rotating the token
  requires updating both the OctoWatch environment and the GitHub audit log
  stream configuration simultaneously. Plan a maintenance window.

### Migration path for existing deployments

1. Generate a new `HEC_TOKEN`: `openssl rand -hex 32`
2. Update `.env`: set `HEC_TOKEN=<value>`, change `INGESTION_MODE=hec`,
   remove all `MINIO_*` variables.
3. Configure GitHub audit log streaming to `https://<host>/services/collector`
   with `Authorization: Splunk <HEC_TOKEN>`.
4. Deploy the new stack. The `minio_data` volume may be archived or deleted
   after confirming events are flowing via the HEC endpoint.

---

## Alternatives Considered

| Alternative | Reason rejected |
|-------------|-----------------|
| Upgrade to MinIO AGPL-3.0 (clustered) | Adds operational complexity; AGPL license remains a concern for organizations distributing modified versions |
| Keep MinIO, pin to last Apache-licensed version | Frozen at a known-vulnerable version with no upstream security fixes |
| Use Valkey as ingestion buffer | Valkey is already in the stack but is not designed for durable message persistence; risk of event loss under memory pressure |
| Use a managed queue (AWS SQS, Azure Service Bus) | Introduces cloud vendor lock-in and additional cost; rejected for a self-hosted-first product |
