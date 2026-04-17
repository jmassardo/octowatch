# OctoWatch Demo Data Seeder

This document describes the plan for generating a realistic, large-scale demo
dataset for the OctoWatch application. The goal is to produce data that
exercises TimescaleDB hypertables at meaningful volume, demonstrates realistic
security posture patterns, and enables compelling live demos.

---

## 1. Target Scale

| Dimension | Target |
|---|---|
| GitHub Organizations | 500 |
| Developers (org members) | 15,000 |
| Repositories | 80,000 |
| Audit log history | 180 days (6 months) |
| Copilot metrics history | 180 days (6 months) |

### Org Distribution (Power-Law)

Real GitHub enterprise accounts are never evenly distributed. The seeder
replicates a Zipf-like power law:

| Tier | Orgs | Members per Org |
|---|---|---|
| Large (e.g., platform, infra) | 5 | 500–1,000 |
| Medium (e.g., product tribes) | 50 | 50–200 |
| Small (e.g., team projects) | 445 | 5–50 |

Total members: `(5 × 750) + (50 × 125) + (445 × 25)` ≈ **18,000 slots**.
After deduplication (users belong to multiple orgs), the deduplicated roster
targets 15,000 unique GitHub logins.

---

## 2. Volume Estimates

### 2.1 Audit Event Rows (`events` hypertable)

The calculation models realistic GitHub audit log traffic:

- **180-day window**: 128 weekdays + 52 weekend days
- **Active user rate**: 70% of users active on any given day
- **Weekday event rate**: ~50 events/user/day (pushes, PRs, code review,
  settings changes, access checks)
- **Weekend event rate**: ~5 events/user/day (light CI/CD, on-call actions)

```
Weekday events:  15,000 × 0.70 × 50 × 128 =  67,200,000
Weekend events:  15,000 × 0.70 ×  5 ×  52 =   2,730,000
─────────────────────────────────────────────────────────
Total events:                                  ~70,000,000
```

The `event_dedup` table mirrors this count (one row per event for global
cross-chunk deduplication), adding another **~70M rows**.

### 2.2 Copilot Metrics Rows

**`copilot_daily_metrics`** — one row per (date, org, metric_type, language,
editor, model) combination:

- 500 orgs × 180 days × ~10 combos (3 languages × 2 editors + 4 aggregate
  metric types) = **~900,000 rows**

**`copilot_seat_snapshots`** — weekly point-in-time snapshots of seat
assignments:

- ~10,000 users with Copilot seats × 26 weekly snapshots = **~260,000 rows**

### 2.3 Reference Table Rows

| Table | Rows |
|---|---|
| `enterprise_orgs` | 500 |
| `org_members` | ~50,000 (many-to-many; avg 3 orgs per user) |
| `repositories` | 80,000 |
| `org_config` | 500 |
| `org_teams` | ~2,500 (5 per org average) |
| `org_team_members` | ~25,000 |
| `external_collaborators` | ~5,000 |

### 2.4 Total Estimated Rows

| Category | Rows |
|---|---|
| `events` | ~70,000,000 |
| `event_dedup` | ~70,000,000 |
| `copilot_daily_metrics` | ~900,000 |
| `copilot_seat_snapshots` | ~260,000 |
| Reference tables (combined) | ~163,500 |
| **Total** | **~141,300,000** |

### 2.5 Estimated Database Size

- **`events` raw**: 70M rows × ~500 bytes/row (action, JSONB payload, IPs,
  geo) ≈ **35 GB**
- **`event_dedup` raw**: 70M × ~80 bytes ≈ **5.6 GB**
- **Other tables**: ~2 GB
- **Raw total**: ~43 GB

TimescaleDB compression (configured with `compress_segmentby = 'org, namespace'`
and `compress_orderby = 'created_at DESC'`) achieves typical **8–12× compression**
for time-series event data. At 10× compression:

- **Compressed `events`**: ~3.5 GB
- **`event_dedup`** (not compressed): ~5.6 GB
- **Other tables + indexes**: ~3 GB
- **Total on-disk**: **~12 GB**

### 2.6 TimescaleDB Chunk Implications

- The `events` hypertable uses 1-week chunk intervals
- 180 days / 7 days = **~26 active chunks**
- The compression policy compresses chunks older than 7 days, so **25 chunks
  will be compressed** and only the most recent chunk will remain uncompressed
- Each compressed chunk holds ~2.7M events; each uncompressed chunk holds
  ~2.7M events at ~1.35 GB before compression
- For the seeder, chunks should be inserted in time order to avoid forcing
  TimescaleDB to create out-of-order chunks

---

## 3. Implementation Options

Six strategies are evaluated. **Option F (Hybrid)** is recommended.

### Option A: Pure Python + SQLAlchemy Bulk Inserts

Use the `faker` library for realistic data generation. Batch rows into lists
of 1,000–5,000 and call `session.bulk_insert_mappings()` or
`conn.execute(table.insert(), rows)`.

**Estimated runtime at target scale:**
- Reference tables (163K rows): ~2–5 minutes
- Event rows (140M rows at ~50K rows/sec): **~45 minutes**
- Total: ~50 minutes with 4 workers

**Pros:**
- Simple Python, no extra dependencies
- Works with existing SQLAlchemy models; column names stay in sync
- Easy to maintain as schema evolves

**Cons:**
- Slow for time-series tables (INSERT overhead per batch)
- Python overhead for 140M rows is significant
- Memory pressure if batches are too large

---

### Option B: Python + psycopg2 COPY Protocol *(Recommended for event data)*

Generate rows as CSV strings in-memory, then use psycopg2's
`copy_expert("COPY events (...) FROM STDIN WITH CSV", io.StringIO(csv))`.
This bypasses the SQL parser, WAL journal latency for individual rows, and
row-level trigger overhead.

**Estimated runtime at target scale:**
- COPY protocol delivers **200K–500K rows/sec** for wide rows on typical
  NVMe storage
- 70M events at 300K rows/sec: **~4 minutes per pass**
- With 4 parallel workers (different time ranges): **~1 minute** for events
- Total including reference tables: **~5–10 minutes**

**Pros:**
- 10–50× faster than INSERT for bulk data
- Low memory overhead (stream line-by-line)
- Handles TimescaleDB hypertables transparently

**Cons:**
- Must avoid the generated `namespace` column (it's `GENERATED ALWAYS AS`)
- Must respect all CHECK constraints in CSV values
- Requires psycopg2 (synchronous), not asyncpg

---

### Option C: timescaledb-parallel-copy

A purpose-built Go CLI tool (`timescaledb-parallel-copy`) that reads CSV from
stdin or file, auto-discovers the hypertable partition key, and distributes
COPY streams across multiple workers.

**Estimated runtime at target scale:**
- Benchmarks show **500K–1M rows/sec** on local PostgreSQL
- 70M events: **~1–2 minutes**

**Pros:**
- Best raw throughput for TimescaleDB hypertables
- Automatically handles chunk routing
- Ideal for CI/CD where you ship pre-generated CSV

**Cons:**
- Requires installing a Go binary in the container or CI environment
- CSV pre-generation step still needed (adds complexity)
- Less portable than pure Python

---

### Option D: factory_boy Factories

Define `factory_boy` `Factory` classes for each model. Good for unit tests
and small seed datasets where you want a few dozen realistic objects.

**Estimated runtime at target scale:**
- ~10–50 rows/sec due to per-object Python overhead
- 140M rows: **days** at target scale

**Pros:**
- Best ergonomics for test fixtures
- Integrates with pytest via `factory_boy` + `pytest-factoryboy`
- Easy relational integrity (SubFactory, LazyAttribute)

**Cons:**
- Far too slow for 140M rows
- Not appropriate for demo volume; only useful for unit test seeds

---

### Option E: Pre-generated pg_dump

Run the seeder once in a controlled environment, then export with `pg_dump`
and ship the compressed dump as a release artifact.

**Estimated artifact size:**
- pg_dump with `--compress=9`: ~1–2 GB (TimescaleDB compression is applied
  on restore)

**Estimated restore time:**
- `pg_restore` from compressed dump: **5–15 minutes** depending on hardware

**Pros:**
- Fastest "time to demo" (restore beats re-generating every time)
- Deterministic: every environment gets exactly the same data
- Useful for QA environments where consistency matters

**Cons:**
- Large artifact to distribute (1–2 GB); must be stored in object storage
- Must be regenerated when schema changes
- Not suitable for CI where disk space or bandwidth is constrained
- TimescaleDB version must match between dump and restore environment

---

### Option F: Hybrid Approach *(Recommended Overall)*

Combine the best characteristics of Options A and B:

1. **Reference data** (`enterprise_orgs`, `org_members`, `repositories`,
   `org_config`, `org_teams`, `org_team_members`, `copilot_seat_snapshots`):
   Use **SQLAlchemy bulk inserts** with batches of 5,000 rows. At 163K rows
   this finishes in **1–3 minutes** and gives you schema validation for free.

2. **Time-series data** (`events`, `event_dedup`, `copilot_daily_metrics`):
   Use **psycopg2 COPY FROM STDIN** with in-memory CSV generation. At 300K
   rows/sec, 70M events take **~4 minutes single-threaded**, or **~1 minute**
   with 4 parallel workers covering non-overlapping time ranges.

**Total estimated runtime: 5–10 minutes**
**Total estimated on-disk size: ~12 GB**

This is the recommended approach. It is implemented in
`scripts/seed_demo_data.py`.

---

## 4. Realistic Data Patterns

### 4.1 Org Distribution

```python
# Power-law org member counts using Zipf distribution (s=1.5)
import numpy as np
counts = np.random.zipf(1.5, 500)
counts = np.clip(counts, 5, 1000)
```

Targeting: 5 orgs ≥ 500 members, 50 orgs 50–200 members, 445 orgs 5–50 members.

### 4.2 Audit Event Types and Frequencies

The seeder generates events with the following approximate distribution
(based on analysis of real GitHub Enterprise audit log samples):

| Action Namespace | Example Actions | Share of Volume |
|---|---|---|
| `push` | `push` | 28% |
| `pull_request` | `pull_request.create`, `.review`, `.merge`, `.close` | 18% |
| `repo` | `repo.create`, `repo.destroy`, `repo.access`, `repo.rename` | 12% |
| `org` | `org.add_member`, `org.remove_member`, `org.update_settings` | 6% |
| `team` | `team.add_member`, `team.remove_member`, `team.create` | 5% |
| `protected_branch` | `protected_branch.create`, `.update`, `.destroy` | 4% |
| `workflows` | `workflows.approve_workflow_run`, `.cancel_workflow_run` | 8% |
| `secret_scanning` | `secret_scanning.alert.create`, `.resolve`, `.dismiss` | 1% |
| `code_scanning` | `code_scanning.alert.created`, `.closed`, `.fixed` | 2% |
| `member` | `member.add`, `member.remove`, `member.change_role` | 3% |
| `repository` | `repository.create`, `.visibility_change`, `.transfer` | 3% |
| `oauth_application` | `oauth_application.create`, `.destroy`, `.token_revoke` | 2% |
| Other | `hook.*`, `deploy_key.*`, `packages.*`, `dependabot.*` | 8% |

### 4.3 Security Events (2–5% of Volume)

For demo impact, 2–5% of events are flagged as "interesting" security events:

- **Failed authentication**: `org.oauth_app_access_denied`, `org.block_user`
  — spikes for 3–5 suspicious users
- **Unusual access times**: events outside 06:00–22:00 UTC for the org's
  primary timezone (indicates off-hours access)
- **Policy violations**: `org.update_member` (changing member role without
  approval), `protected_branch.destroy`
- **Secret scanning findings**: 15–30 active `secret_scanning.alert.create`
  events that are never resolved (unresolved critical findings)
- **External collaborator sprawl**: 200+ `external_collaborators` added over
  the period with no removal events

### 4.4 Temporal Patterns

**Time-of-day distribution** (modeled as a mixture of two Gaussians):

```
Peak 1: 14:00–18:00 UTC (US Pacific 06:00–10:00 + EU afternoon)  → 40% of events
Peak 2: 09:00–13:00 UTC (EU morning + US East morning)            → 35% of events
Off-hours (18:00–09:00 UTC)                                        → 25% of events
```

**Weekday vs weekend**: weekday volume is 10× weekend volume.

**6-month growth trend**: event volume grows linearly by 20% over the period
to simulate org growth (older events have slightly lower volume per user).

### 4.5 Copilot Usage Patterns

| Metric | Target Range |
|---|---|
| Acceptance rate | 25–40% (varies by language and user persona) |
| Languages | TypeScript/JavaScript 40%, Python 25%, Go 10%, Java 10%, other 15% |
| Editors | VS Code 65%, JetBrains 25%, Neovim/other 10% |
| Active Copilot users | 60–80% of org members (varies by org; some orgs 100%) |
| Lines accepted per active user per day | 15–80 (power users: 200+) |

### 4.6 Developer Personas

Three personas drive activity distribution:

| Persona | % of Users | % of Events Generated |
|---|---|---|
| Power users | 5% | 40% |
| Regular contributors | 60% | 55% |
| Occasional / inactive | 35% | 5% |

Power users have activity on 95% of weekdays; occasional users on ~15%.

---

## 5. Seeder Script Architecture

### 5.1 CLI Interface

```bash
python scripts/seed_demo_data.py \
  --orgs 500 \
  --users 15000 \
  --repos 80000 \
  --days 180 \
  --seed 42 \           # for reproducible random data
  --batch-size 5000 \   # rows per bulk insert batch (reference tables)
  --workers 4 \         # parallel psycopg2 COPY workers for event generation
  --skip-events \       # seed only reference data (fast, ~2 min)
  --resume \            # skip already-completed phases using .seed_progress.json
  --dry-run             # print volume estimates without writing to DB
```

### 5.2 Execution Order (Dependency Graph)

```
1. seed_orgs()             → enterprise_orgs, org_config
2. seed_users()            → org_members, org_teams, org_team_members
3. seed_repos()            → repositories
4. seed_copilot_seats()    → copilot_seat_snapshots
5. seed_copilot_metrics()  → copilot_daily_metrics    [COPY protocol]
6. seed_events()           → events, event_dedup      [COPY protocol, parallel]
```

### 5.3 Parallelism Strategy

Event generation is parallelized by time range. With `--workers 4`, the 180-day
window is split into 4 × 45-day segments. Each worker maintains its own
psycopg2 connection and writes to a different set of TimescaleDB chunks,
avoiding write contention.

---

## 6. Resumability and Idempotency

### 6.1 Checkpoint File

The script writes `.seed_progress.json` in the current working directory after
each phase completes:

```json
{
  "seed": 42,
  "orgs": "done",
  "users": "done",
  "repos": "in_progress",
  "events": "pending",
  "copilot_seats": "pending",
  "copilot_metrics": "pending",
  "completed_at": null
}
```

When `--resume` is passed, phases marked `"done"` are skipped.

### 6.2 Idempotency Modes

| Mode | Behavior |
|---|---|
| Default (first run) | `TRUNCATE ... CASCADE` all target tables, then insert |
| `--resume` | Skip completed phases; use `ON CONFLICT DO NOTHING` for partial phases |
| `--dry-run` | Print row count estimates; no writes |

The `events` hypertable cannot be truncated without cascade due to the
compression policy; the seeder uses `DELETE FROM events WHERE ingestion_source = 'hec'`
scoped to `source_file_path LIKE 'demo-seed/%'` to allow safe re-runs
without touching real ingested data.

### 6.3 Partial Failure Recovery

If the script crashes mid-phase (e.g., during event COPY), the checkpoint
remains at `"in_progress"`. On the next `--resume` run, the seeder:

1. Deletes any demo events in the partial time window
2. Re-generates that time window from scratch using the deterministic seed

---

## 7. Where It Lives

### 7.1 Files

| Path | Purpose |
|---|---|
| `scripts/seed_demo_data.py` | Main seeder script |
| `scripts/requirements-seed.txt` | Python dependencies for the seeder |
| `.seed_progress.json` | Checkpoint file (gitignored) |
| `docs/demo-data-seeder.md` | This document |

### 7.2 Python Dependencies

Add to `scripts/requirements-seed.txt`:

```
psycopg2-binary>=2.9
faker>=24.0
tqdm>=4.66
python-dotenv>=1.0
```

No SQLAlchemy is required for the seeder — it uses psycopg2 directly for
performance. The seeder script does import the model files to read table and
column names, but does not run the async engine.

### 7.3 Running Against the Docker Compose Stack

```bash
# 1. Start the stack (db must be running and migrated)
docker compose up -d db
docker compose run --rm api alembic upgrade head

# 2. Install seeder dependencies (host machine or a throw-away container)
pip install -r scripts/requirements-seed.txt

# 3. Export the DATABASE_URL using the sync psycopg2 driver
#    (strip the +asyncpg driver suffix from .env)
export DATABASE_URL="postgresql://appuser:PASSWORD@localhost:5432/audit_logs"

# 4. Run the seeder (reference data only, fast)
python scripts/seed_demo_data.py --orgs 500 --users 15000 --repos 80000 \
  --days 180 --seed 42 --skip-events

# 5. Run the full seeder including events (takes 5–10 minutes)
python scripts/seed_demo_data.py --orgs 500 --users 15000 --repos 80000 \
  --days 180 --seed 42 --workers 4

# 6. Or run inside the compose network without port mapping:
docker compose run --rm \
  -e DATABASE_URL="postgresql://appuser:PASSWORD@db:5432/audit_logs" \
  api python /app/../scripts/seed_demo_data.py --orgs 500 --users 15000 \
  --repos 80000 --days 180 --seed 42
```

### 7.4 Gitignore

Add to `.gitignore`:
```
.seed_progress.json
```

---

## 8. Future Extensions

- **Makefile target**: `make seed-demo` to run with canonical flags
- **Docker Compose profile**: `profiles: [seed]` service that runs the
  seeder and exits, ensuring correct network + env setup
- **Grafana dashboard annotations**: emit a JSON file with seed run metadata
  so dashboards can mark the "demo period" boundary
- **Deterministic re-generation**: with `--seed 42` the output is always
  identical, enabling snapshot testing of reports and detections against known
  demo data
