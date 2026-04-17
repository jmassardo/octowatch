#!/usr/bin/env python3
"""OctoWatch demo data seeder.

Generates a realistic large-scale dataset for the OctoWatch application:
  - 500 GitHub organizations (power-law member distribution)
  - 15,000 developers with org memberships
  - 80,000 repositories
  - 180 days of audit log events (~70M rows via COPY protocol)
  - 180 days of Copilot daily metrics

See docs/demo-data-seeder.md for full design rationale and volume estimates.

Usage::

    export DATABASE_URL="postgresql://appuser:PASSWORD@localhost:5432/audit_logs"
    python scripts/seed_demo_data.py --orgs 500 --users 15000 --repos 80000 \\
        --days 180 --seed 42 --workers 4

    # Enterprise scale (matching real customer: 35k devs, 125 orgs, 500 eps):
    #   python scripts/seed_demo_data.py --scale enterprise --seed 42
    # Or manually:
    #   python scripts/seed_demo_data.py --orgs 125 --users 39000 --repos 120000 \\
    #       --days 180 --integration-bots 300 --bot-eps 450 --seed 42 --workers 4

Requirements (scripts/requirements-seed.txt)::

    psycopg2-binary>=2.9
    faker>=24.0
    tqdm>=4.66
    python-dotenv>=1.0
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import multiprocessing
import os
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional imports — fail with a clear message if missing
# ---------------------------------------------------------------------------
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    sys.exit(
        "psycopg2-binary is required. Install with:\n"
        "  pip install psycopg2-binary"
    )

try:
    from faker import Faker
except ImportError:
    sys.exit(
        "faker is required. Install with:\n"
        "  pip install faker"
    )

try:
    from tqdm import tqdm
except ImportError:
    # Graceful degradation: replace tqdm with a no-op wrapper
    def tqdm(iterable=None, **kwargs):  # type: ignore[no-redef]
        if iterable is not None:
            return iterable
        class _DummyTqdm:
            def update(self, n=1): pass
            def set_postfix(self, **kw): pass
            def close(self): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _DummyTqdm()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; DATABASE_URL can be set directly

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHECKPOINT_FILE = Path(".seed_progress.json")
DEMO_SOURCE_FILE_PREFIX = "demo-seed/"

# Audit event action distribution (action → relative weight)
# namespace is a generated column (split_part(action, '.', 1)) — never inserted.
EVENT_ACTIONS: list[tuple[str, int]] = [
    # push namespace
    ("push", 2800),
    # pull_request namespace
    ("pull_request.create", 600),
    ("pull_request.review", 500),
    ("pull_request.merge", 400),
    ("pull_request.close", 300),
    # repo namespace
    ("repo.create", 300),
    ("repo.destroy", 20),
    ("repo.access", 500),
    ("repo.rename", 30),
    ("repo.archived", 15),
    # org namespace
    ("org.add_member", 250),
    ("org.remove_member", 100),
    ("org.update_member", 80),
    ("org.update_settings", 40),
    # team namespace
    ("team.add_member", 200),
    ("team.remove_member", 80),
    ("team.create", 30),
    ("team.destroy", 10),
    # protected_branch namespace
    ("protected_branch.create", 80),
    ("protected_branch.update", 60),
    ("protected_branch.destroy", 15),
    # workflows namespace
    ("workflows.approve_workflow_run", 400),
    ("workflows.cancel_workflow_run", 150),
    ("workflows.completed_workflow_run", 200),
    # secret_scanning namespace (2% — demo-impactful security events)
    ("secret_scanning.alert.create", 60),
    ("secret_scanning.alert.resolve", 30),
    ("secret_scanning.alert.dismiss", 15),
    # code_scanning namespace
    ("code_scanning.alert.created", 80),
    ("code_scanning.alert.closed", 50),
    ("code_scanning.alert.fixed", 40),
    # member namespace
    ("member.add", 120),
    ("member.remove", 40),
    ("member.change_role", 20),
    # repository namespace
    ("repository.create", 120),
    ("repository.visibility_change", 15),
    ("repository.transfer", 10),
    # oauth_application namespace
    ("oauth_application.create", 30),
    ("oauth_application.destroy", 10),
    ("oauth_application.token_revoke", 20),
    # hook namespace
    ("hook.create", 40),
    ("hook.destroy", 20),
    # deploy_key namespace
    ("deploy_key.create", 30),
    ("deploy_key.destroy", 15),
]

# Pre-compute cumulative weights for fast weighted sampling
_ACTION_NAMES = [a for a, _ in EVENT_ACTIONS]
_ACTION_WEIGHTS = [w for _, w in EVENT_ACTIONS]

# Bot/integration audit event distribution
# Integrations (Jira, Rally, Aha!, GitHub Apps) generate high-volume API events:
# - issue/PR linkage events, webhook deliveries, OAuth token usage, repo reads
BOT_EVENT_WEIGHTS: list[tuple[str, float]] = [
    ("integration.installation.repositories_added", 50),
    ("integration.installation", 40),
    ("repo.access", 300),          # frequent read access checks
    ("pull_request.review_requested", 200),
    ("issues.labeled", 400),       # Jira/Rally label syncs
    ("issues.milestoned", 150),
    ("project.create", 50),
    ("project_column.create", 30),
    ("project_card.create", 200),  # Rally/Aha! card syncs
    ("pull_request.edited", 300),  # PR description updates from bots
    ("repository_vulnerability_alert.create", 80),
    ("org.add_member", 20),
    ("team.add_member", 40),
    ("protected_branch.update_protection_rule", 30),
    ("oauth_application.generate_client_secret", 10),
    ("hook.create", 20),
    ("hook.events_changed", 15),
    ("workflows.prepared_workflow_job", 500),  # Actions integration events
    ("check_run.create", 600),                 # CI integrations creating check runs
    ("check_suite.completed", 400),
    ("deployment.create", 100),
    ("deployment_status.create", 200),
]

# Pre-compute cumulative weights for fast weighted bot event sampling
_BOT_ACTION_NAMES = [a for a, _ in BOT_EVENT_WEIGHTS]
_BOT_ACTION_WEIGHTS = [w for _, w in BOT_EVENT_WEIGHTS]

LANGUAGES = [
    ("typescript", 0.25),
    ("javascript", 0.15),
    ("python", 0.25),
    ("go", 0.10),
    ("java", 0.10),
    ("ruby", 0.05),
    ("rust", 0.04),
    ("csharp", 0.03),
    ("cpp", 0.03),
]

EDITORS = [
    ("vscode", 0.65),
    ("jetbrains", 0.25),
    ("neovim", 0.07),
    ("other", 0.03),
]

COPILOT_MODELS = ["gpt-4o-copilot", "claude-3.5-sonnet-copilot"]
ORG_PLANS = ["enterprise", "enterprise", "enterprise", "team", "free"]
VISIBILITY_OPTIONS = ["private", "private", "private", "internal", "public"]
BRANCH_NAMES = ["main", "main", "main", "master", "develop"]

# Country codes for geo data (weighted toward US/EU/Asia)
GEO_COUNTRIES = [
    ("US", 0.35), ("GB", 0.10), ("DE", 0.08), ("CA", 0.07), ("FR", 0.06),
    ("AU", 0.05), ("IN", 0.05), ("JP", 0.04), ("NL", 0.04), ("BR", 0.03),
    ("SE", 0.02), ("SG", 0.02), ("ES", 0.02), ("IT", 0.02), ("PL", 0.02),
    ("CH", 0.01), ("NO", 0.01), ("DK", 0.01),
]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed OctoWatch with realistic demo data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--orgs", type=int, default=500, help="Number of GitHub organizations")
    parser.add_argument("--users", type=int, default=15_000, help="Number of unique developers")
    parser.add_argument("--repos", type=int, default=80_000, help="Number of repositories")
    parser.add_argument(
        "--days", type=int, default=180, help="Days of historical data to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5_000,
        help="Rows per bulk insert batch (reference tables)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, multiprocessing.cpu_count() // 2),
        help="Parallel workers for event COPY (default: half CPU count)",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="Seed only reference data; skip event and metrics generation",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint; skip already-completed phases",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print volume estimates without writing to the database",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help=(
            "PostgreSQL connection URL (psycopg2 sync driver). "
            "Defaults to $DATABASE_URL. Strip '+asyncpg' if copying from .env."
        ),
    )
    parser.add_argument(
        "--integration-bots",
        type=int,
        default=0,
        metavar="N",
        help="Number of integration bot accounts to simulate (Jira, Rally, Aha!, GitHub Apps, etc.)",
    )
    parser.add_argument(
        "--bot-eps",
        type=float,
        default=50.0,
        metavar="EPS",
        help="Sustained events-per-second rate for all bots combined (spread evenly across --days)",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default=None,
        choices=["small", "medium", "large", "enterprise"],
        help=(
            "Preset scale profile. Overrides --orgs/--users/--repos/--days/--integration-bots/--bot-eps. "
            "small=PoC (50 orgs, 1k users), medium=SMB (200 orgs, 5k users), "
            "large=mid-market (500 orgs, 15k users, 100 bots), "
            "enterprise=large customer (125 orgs, 39k users, 300 bots, 450 bot-eps)"
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_connection(database_url: str) -> "psycopg2.connection":
    """Return a psycopg2 synchronous connection.

    Strips the SQLAlchemy driver prefix (+asyncpg, +psycopg2) so the URL
    from .env can be used directly.
    """
    url = database_url
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
            break
    # Also strip sslmode for local Docker connections if needed
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# Checkpoint management
# ---------------------------------------------------------------------------

PHASES = ["orgs", "users", "repos", "copilot_seats", "copilot_metrics", "events", "bot_events"]

# Scale presets for common deployment sizes
SCALE_PRESETS: dict[str, dict[str, Any]] = {
    "small": {
        "orgs": 50,
        "users": 1_000,
        "repos": 5_000,
        "days": 90,
        "integration_bots": 0,
        "bot_eps": 0.0,
    },
    "medium": {
        "orgs": 200,
        "users": 5_000,
        "repos": 20_000,
        "days": 180,
        "integration_bots": 50,
        "bot_eps": 20.0,
    },
    "large": {
        "orgs": 500,
        "users": 15_000,
        "repos": 80_000,
        "days": 180,
        "integration_bots": 100,
        "bot_eps": 80.0,
    },
    "enterprise": {
        "orgs": 125,
        "users": 39_000,   # 35k devs + 4k PMs
        "repos": 120_000,
        "days": 180,
        "integration_bots": 300,
        "bot_eps": 450.0,  # ~94% of 500 eps total
    },
}


def load_checkpoint(seed: int) -> dict[str, str]:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        if data.get("seed") == seed:
            return data
    return {"seed": seed, **{phase: "pending" for phase in PHASES}}


def save_checkpoint(checkpoint: dict[str, Any]) -> None:
    CHECKPOINT_FILE.write_text(json.dumps(checkpoint, indent=2, default=str))


def mark_phase(checkpoint: dict[str, Any], phase: str, status: str) -> None:
    checkpoint[phase] = status
    if status == "done" and all(checkpoint.get(p) == "done" for p in PHASES):
        checkpoint["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_checkpoint(checkpoint)


def should_skip(checkpoint: dict[str, Any], phase: str, resume: bool) -> bool:
    return resume and checkpoint.get(phase) == "done"


# ---------------------------------------------------------------------------
# Realistic data generators
# ---------------------------------------------------------------------------

def _weighted_choice(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    """Pick a value from a list of (value, weight) pairs."""
    values, weights = zip(*choices)
    return rng.choices(values, weights=weights, k=1)[0]


def _power_law_member_counts(rng: random.Random, n_orgs: int, total_users: int) -> list[int]:
    """Generate org member counts following a power-law distribution.

    Ensures the sum is approximately total_users (accounting for multi-org membership).
    """
    # Use Zipf-like distribution: count[i] ∝ 1/i^1.5
    raw = [max(5, int(total_users / (i ** 1.5))) for i in range(1, n_orgs + 1)]
    # Scale to target ~2× total_users (users belong to multiple orgs on average)
    target_sum = total_users * 2
    current_sum = sum(raw)
    scaled = [max(5, int(c * target_sum / current_sum)) for c in raw]
    rng.shuffle(scaled)
    return scaled


def generate_org_name(fake: Faker, rng: random.Random) -> tuple[str, str]:
    """Return (org_login, display_name) pair."""
    words = [
        "cloud", "data", "infra", "platform", "core", "eng", "dev", "ops",
        "security", "api", "services", "labs", "tech", "digital", "global",
    ]
    suffixes = ["io", "hq", "co", "inc", "corp", "systems", "group", "works"]
    slug = f"{rng.choice(words)}-{rng.choice(words)}-{rng.choice(suffixes)}"
    # Ensure uniqueness via a short numeric suffix is handled by caller
    display = slug.replace("-", " ").title()
    return slug, display


def generate_github_login(fake: Faker, rng: random.Random, idx: int) -> str:
    """Generate a realistic GitHub username."""
    styles = [
        lambda: f"{fake.first_name().lower()}{fake.last_name().lower()}{rng.randint(1, 99)}",
        lambda: f"{fake.first_name().lower()}-{fake.last_name().lower()}",
        lambda: f"{fake.word()}{rng.randint(100, 9999)}",
        lambda: fake.user_name(),
    ]
    login = rng.choice(styles)()
    # Sanitize: only alphanumeric and hyphens, max 39 chars
    login = "".join(c if c.isalnum() or c == "-" else "" for c in login)[:39]
    return login or f"user{idx}"


# ---------------------------------------------------------------------------
# Phase 1: Seed organizations
# ---------------------------------------------------------------------------

def seed_orgs(
    conn: "psycopg2.connection",
    fake: Faker,
    rng: random.Random,
    n_orgs: int,
    n_users: int,
    batch_size: int,
    enterprise_slug: str = "demo-enterprise",
) -> list[dict[str, Any]]:
    """Insert rows into enterprise_orgs and org_config.

    Returns a list of org dicts for use by downstream seeders.
    """
    print(f"\n[1/7] Seeding {n_orgs} organizations...")

    member_counts = _power_law_member_counts(rng, n_orgs, n_users)

    orgs: list[dict[str, Any]] = []
    for i in range(n_orgs):
        slug_base, _ = generate_org_name(fake, rng)
        slug = f"{slug_base}-{i:04d}"  # guarantee uniqueness
        orgs.append({
            "enterprise_slug": enterprise_slug,
            "org_login": slug,
            "org_id": 100_000 + i,
            "visibility": "private",
            "plan": rng.choice(ORG_PLANS),
            "member_count": member_counts[i],
            "synced_at": datetime.now(timezone.utc),
        })

    cur = conn.cursor()
    # Truncate before insert (safe for reference tables)
    cur.execute("TRUNCATE enterprise_orgs CASCADE")
    cur.execute("TRUNCATE org_config CASCADE")

    # Bulk insert enterprise_orgs
    rows_inserted = 0
    for batch_start in tqdm(range(0, len(orgs), batch_size), desc="  enterprise_orgs"):
        batch = orgs[batch_start : batch_start + batch_size]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO enterprise_orgs
                (enterprise_slug, org_login, org_id, visibility, plan,
                 member_count, synced_at)
            VALUES %s
            ON CONFLICT (enterprise_slug, org_login) DO NOTHING
            """,
            [
                (
                    o["enterprise_slug"],
                    o["org_login"],
                    o["org_id"],
                    o["visibility"],
                    o["plan"],
                    o["member_count"],
                    o["synced_at"],
                )
                for o in batch
            ],
            page_size=batch_size,
        )
        rows_inserted += len(batch)

    # Bulk insert org_config (one row per org)
    org_config_rows = [
        (
            o["org_login"],
            round(rng.uniform(15.0, 25.0), 2) if rng.random() < 0.3 else None,
        )
        for o in orgs
    ]
    for batch_start in tqdm(range(0, len(org_config_rows), batch_size), desc="  org_config"):
        batch = org_config_rows[batch_start : batch_start + batch_size]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO org_config (org_slug, copilot_cost_per_seat)
            VALUES %s
            ON CONFLICT (org_slug) DO NOTHING
            """,
            batch,
            page_size=batch_size,
        )

    conn.commit()
    print(f"  ✓ Inserted {rows_inserted} orgs")
    return orgs


# ---------------------------------------------------------------------------
# Phase 2: Seed users / org memberships
# ---------------------------------------------------------------------------

def seed_users(
    conn: "psycopg2.connection",
    fake: Faker,
    rng: random.Random,
    orgs: list[dict[str, Any]],
    n_users: int,
    batch_size: int,
) -> list[str]:
    """Insert rows into org_members.

    Returns a list of all unique GitHub login strings for downstream use.
    """
    print(f"\n[2/7] Seeding {n_users} users across {len(orgs)} orgs...")

    # Generate the global user roster
    logins: list[str] = []
    seen_logins: set[str] = set()
    for i in range(n_users):
        login = generate_github_login(fake, rng, i)
        while login in seen_logins:
            login = f"{login}{rng.randint(1, 999)}"
        seen_logins.add(login)
        logins.append(login)

    cur = conn.cursor()
    cur.execute("TRUNCATE org_members CASCADE")

    # Distribute users into orgs according to member_count targets
    org_memberships: list[tuple] = []  # (org, login, github_id, role, mfa_enabled)
    github_id_counter = 1_000_000

    for org_idx, org in enumerate(tqdm(orgs, desc="  distributing users")):
        target_count = min(org["member_count"], n_users)
        # Sample users for this org (with replacement across orgs — realistic)
        org_users = rng.sample(logins, min(target_count, len(logins)))
        for login in org_users:
            role = "owner" if rng.random() < 0.05 else "member"
            mfa_enabled = None if rng.random() < 0.1 else rng.random() > 0.15
            org_memberships.append((
                org["org_login"],
                login,
                github_id_counter,
                role,
                mfa_enabled,
                datetime.now(timezone.utc),
            ))
            github_id_counter += 1

    rng.shuffle(org_memberships)

    for batch_start in tqdm(range(0, len(org_memberships), batch_size), desc="  org_members"):
        batch = org_memberships[batch_start : batch_start + batch_size]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO org_members (org, github_login, github_id, role, mfa_enabled, synced_at)
            VALUES %s
            ON CONFLICT (org, github_login) DO NOTHING
            """,
            batch,
            page_size=batch_size,
        )

    conn.commit()
    print(f"  ✓ Inserted {len(org_memberships):,} org memberships for {n_users:,} unique users")
    return logins


# ---------------------------------------------------------------------------
# Phase 3: Seed repositories
# ---------------------------------------------------------------------------

def seed_repos(
    conn: "psycopg2.connection",
    fake: Faker,
    rng: random.Random,
    orgs: list[dict[str, Any]],
    n_repos: int,
    batch_size: int,
) -> None:
    """Insert rows into the repositories table."""
    print(f"\n[3/7] Seeding {n_repos:,} repositories...")

    cur = conn.cursor()
    cur.execute("TRUNCATE repositories CASCADE")

    # Distribute repos across orgs proportionally to member count
    total_members = sum(o["member_count"] for o in orgs)
    repo_counts = [
        max(1, round(n_repos * o["member_count"] / total_members))
        for o in orgs
    ]

    repo_id_counter = 200_000_000
    now = datetime.now(timezone.utc)
    repo_batch: list[tuple] = []
    total_inserted = 0

    tech_words = [
        "api", "service", "worker", "frontend", "backend", "client", "server",
        "utils", "lib", "sdk", "cli", "dashboard", "pipeline", "gateway",
        "engine", "platform", "core", "agent", "proxy", "scheduler",
    ]

    for org_idx, (org, count) in enumerate(tqdm(
        zip(orgs, repo_counts), total=len(orgs), desc="  repositories"
    )):
        for j in range(count):
            name_parts = [rng.choice(tech_words) for _ in range(rng.randint(1, 3))]
            repo_name = "-".join(name_parts) + f"-{j:04d}"
            pushed_delta = timedelta(days=rng.randint(0, 180))

            repo_batch.append((
                org["org_login"],
                repo_name,
                repo_id_counter,
                rng.choice(VISIBILITY_OPTIONS),
                rng.choice(BRANCH_NAMES),
                rng.random() < 0.03,  # archived
                rng.random() < 0.15,  # fork
                now - pushed_delta,
                now,
            ))
            repo_id_counter += 1

            if len(repo_batch) >= batch_size:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO repositories
                        (org, repo_name, repo_id, visibility, default_branch,
                         archived, fork, pushed_at, synced_at)
                    VALUES %s
                    ON CONFLICT (org, repo_name) DO NOTHING
                    """,
                    repo_batch,
                    page_size=batch_size,
                )
                total_inserted += len(repo_batch)
                repo_batch = []

    # Flush remaining
    if repo_batch:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO repositories
                (org, repo_name, repo_id, visibility, default_branch,
                 archived, fork, pushed_at, synced_at)
            VALUES %s
            ON CONFLICT (org, repo_name) DO NOTHING
            """,
            repo_batch,
            page_size=batch_size,
        )
        total_inserted += len(repo_batch)

    conn.commit()
    print(f"  ✓ Inserted {total_inserted:,} repositories")


# ---------------------------------------------------------------------------
# Phase 4: Seed Copilot seat snapshots
# ---------------------------------------------------------------------------

def seed_copilot_seats(
    conn: "psycopg2.connection",
    rng: random.Random,
    orgs: list[dict[str, Any]],
    logins: list[str],
    n_days: int,
    batch_size: int,
    start_date: date,
) -> None:
    """Insert weekly Copilot seat snapshots into copilot_seat_snapshots."""
    print(f"\n[4/7] Seeding Copilot seat snapshots...")

    cur = conn.cursor()
    cur.execute("TRUNCATE copilot_seat_snapshots CASCADE")

    # Take weekly snapshots (every 7 days)
    snapshot_dates = [start_date + timedelta(days=i) for i in range(0, n_days, 7)]
    editors_for_seat = [e for e, _ in EDITORS]
    editor_weights = [w for _, w in EDITORS]

    rows: list[tuple] = []
    total_inserted = 0

    for org in tqdm(orgs, desc="  copilot_seats"):
        # 60–80% of org members have Copilot
        copilot_fraction = rng.uniform(0.6, 0.85)
        # Build a stable set of users with Copilot for this org
        pool = logins[:min(org["member_count"], len(logins))]
        copilot_users = rng.sample(pool, max(1, int(len(pool) * copilot_fraction)))

        for snap_date in snapshot_dates:
            for login in copilot_users:
                last_activity_delta = timedelta(days=rng.randint(0, 7))
                rows.append((
                    snap_date,
                    org["org_login"],
                    login,
                    "business",
                    datetime.combine(snap_date, datetime.min.time(), tzinfo=timezone.utc)
                    - last_activity_delta,
                    rng.choices(editors_for_seat, weights=editor_weights, k=1)[0],
                    datetime.now(timezone.utc),
                ))

                if len(rows) >= batch_size:
                    psycopg2.extras.execute_values(
                        cur,
                        """
                        INSERT INTO copilot_seat_snapshots
                            (snapshot_date, org_slug, github_login, plan_type,
                             last_activity_at, last_activity_editor, created_at)
                        VALUES %s
                        ON CONFLICT (snapshot_date, org_slug, github_login) DO NOTHING
                        """,
                        rows,
                        page_size=batch_size,
                    )
                    total_inserted += len(rows)
                    rows = []

    if rows:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO copilot_seat_snapshots
                (snapshot_date, org_slug, github_login, plan_type,
                 last_activity_at, last_activity_editor, created_at)
            VALUES %s
            ON CONFLICT (snapshot_date, org_slug, github_login) DO NOTHING
            """,
            rows,
            page_size=batch_size,
        )
        total_inserted += len(rows)

    conn.commit()
    print(f"  ✓ Inserted {total_inserted:,} seat snapshots")


# ---------------------------------------------------------------------------
# Phase 5: Seed Copilot daily metrics
# ---------------------------------------------------------------------------

def seed_copilot_metrics(
    conn: "psycopg2.connection",
    rng: random.Random,
    orgs: list[dict[str, Any]],
    n_days: int,
    batch_size: int,
    start_date: date,
) -> None:
    """Insert rows into copilot_daily_metrics using bulk inserts."""
    print(f"\n[5/7] Seeding Copilot daily metrics...")

    cur = conn.cursor()
    cur.execute("TRUNCATE copilot_daily_metrics CASCADE")

    lang_names = [l for l, _ in LANGUAGES]
    lang_weights = [w for _, w in LANGUAGES]
    editor_names = [e for e, _ in EDITORS]
    editor_weights = [w for _, w in EDITORS]

    rows: list[tuple] = []
    total_inserted = 0
    all_dates = [start_date + timedelta(days=d) for d in range(n_days)]

    for org in tqdm(orgs, desc="  copilot_metrics"):
        base_users = max(5, int(org["member_count"] * rng.uniform(0.5, 0.8)))
        # Aggregate "totals" metric type (one per org per day)
        for day in all_dates:
            weekday = day.weekday()
            activity_factor = 1.0 if weekday < 5 else 0.15
            growth_factor = 1.0 + 0.2 * (all_dates.index(day) / len(all_dates))
            active = max(1, int(base_users * activity_factor * growth_factor * rng.uniform(0.7, 1.0)))
            engaged = max(1, int(active * rng.uniform(0.6, 0.9)))
            total_suggestions = engaged * rng.randint(30, 120)
            acceptance_rate = rng.uniform(0.25, 0.40)
            total_acceptances = int(total_suggestions * acceptance_rate)

            rows.append((
                day,
                org["org_login"],
                "totals",              # metric_type
                None,                  # language
                None,                  # editor
                None,                  # model
                active,
                engaged,
                total_suggestions,
                total_acceptances,
                total_suggestions * rng.randint(3, 8),      # lines suggested
                total_acceptances * rng.randint(3, 8),      # lines accepted
                round(acceptance_rate, 4),
                datetime.now(timezone.utc),
            ))

        # Per-language breakdown
        for day in all_dates:
            weekday = day.weekday()
            activity_factor = 1.0 if weekday < 5 else 0.15
            for lang in rng.choices(lang_names, weights=lang_weights, k=3):
                frac = rng.uniform(0.1, 0.5)
                suggestions = max(1, int(base_users * activity_factor * frac * rng.randint(10, 40)))
                ar = rng.uniform(0.20, 0.45)
                acceptances = int(suggestions * ar)
                editor = rng.choices(editor_names, weights=editor_weights, k=1)[0]

                rows.append((
                    day,
                    org["org_login"],
                    "breakdown",
                    lang,
                    editor,
                    rng.choice(COPILOT_MODELS),
                    max(1, int(base_users * frac * activity_factor)),
                    max(1, int(base_users * frac * activity_factor * 0.8)),
                    suggestions,
                    acceptances,
                    suggestions * rng.randint(3, 8),
                    acceptances * rng.randint(3, 8),
                    round(ar, 4),
                    datetime.now(timezone.utc),
                ))

        if len(rows) >= batch_size:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO copilot_daily_metrics
                    (date, org_slug, metric_type, language, editor, model,
                     active_users, engaged_users, total_suggestions,
                     total_acceptances, total_lines_suggested,
                     total_lines_accepted, acceptance_rate, synced_at)
                VALUES %s
                ON CONFLICT (date, org_slug, metric_type, language, editor, model)
                    DO NOTHING
                """,
                rows,
                page_size=batch_size,
            )
            total_inserted += len(rows)
            rows = []

    if rows:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO copilot_daily_metrics
                (date, org_slug, metric_type, language, editor, model,
                 active_users, engaged_users, total_suggestions,
                 total_acceptances, total_lines_suggested,
                 total_lines_accepted, acceptance_rate, synced_at)
            VALUES %s
            ON CONFLICT (date, org_slug, metric_type, language, editor, model)
                DO NOTHING
            """,
            rows,
            page_size=batch_size,
        )
        total_inserted += len(rows)

    conn.commit()
    print(f"  ✓ Inserted {total_inserted:,} copilot metric rows")


# ---------------------------------------------------------------------------
# Phase 6: Seed audit events (COPY protocol)
# ---------------------------------------------------------------------------

def _generate_event_csv_chunk(
    *,
    org_logins: list[str],
    repo_names_by_org: dict[str, list[str]],
    logins: list[str],
    start_dt: datetime,
    end_dt: datetime,
    seed: int,
    worker_id: int,
    n_days_total: int,
) -> io.StringIO:
    """Generate a CSV buffer of events for the given time window.

    Called in worker processes. Uses a deterministic per-worker seed so that
    multi-worker runs produce the same data as a single-worker run.

    Returns an io.StringIO with CSV data ready for COPY FROM STDIN.
    """
    rng = random.Random(seed + worker_id * 997)
    fake = Faker()
    fake.seed_instance(seed + worker_id * 997)

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    country_codes = [c for c, _ in GEO_COUNTRIES]
    country_weights = [w for _, w in GEO_COUNTRIES]

    current = start_dt
    one_hour = timedelta(hours=1)

    # Determine the number of days in this worker's window
    window_days = max(1, (end_dt - start_dt).days)

    while current < end_dt:
        weekday = current.weekday()
        # Events per hour varies by time-of-day (two Gaussians: 9-13 UTC, 14-18 UTC)
        hour = current.hour
        if 9 <= hour <= 13:
            hourly_multiplier = 1.8
        elif 14 <= hour <= 18:
            hourly_multiplier = 1.5
        elif 6 <= hour < 9 or 18 < hour <= 22:
            hourly_multiplier = 0.6
        else:
            hourly_multiplier = 0.15  # off-hours

        weekend_factor = 0.10 if weekday >= 5 else 1.0
        # Growth trend: 20% more events at end of period vs start
        elapsed_days = (current - start_dt).days
        growth_factor = 1.0 + 0.20 * (elapsed_days / max(1, window_days))

        # Base: with 15000 users, 50 events/user/day / 24h → ~31K events/hour peak
        # Scaled down per worker for the org slice
        n_orgs_slice = len(org_logins)
        events_this_hour = max(
            0,
            int(
                n_orgs_slice
                * 60  # base events per org per hour
                * weekend_factor
                * hourly_multiplier
                * growth_factor
                * rng.uniform(0.8, 1.2)
            ),
        )

        for _ in range(events_this_hour):
            event_ts = current + timedelta(seconds=rng.randint(0, 3599))
            org = rng.choice(org_logins)
            actor = rng.choice(logins)
            action = rng.choices(_ACTION_NAMES, weights=_ACTION_WEIGHTS, k=1)[0]

            repos = repo_names_by_org.get(org, [])
            repo = rng.choice(repos) if repos and "repo" in action or "push" in action else None

            country = rng.choices(country_codes, weights=country_weights, k=1)[0]
            # Generate a plausible IP — using simple ranges, not real geo data
            source_ip = f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"

            document_id = str(uuid.UUID(int=rng.getrandbits(128)))

            # Minimal JSONB payload — add more fields as needed for demo queries
            data_payload = json.dumps({
                "action": action,
                "@timestamp": event_ts.isoformat(),
                "actor": actor,
                "org": org,
                **({"repo": repo} if repo else {}),
            })

            writer.writerow([
                document_id,            # document_id
                event_ts.isoformat(),   # created_at
                event_ts.isoformat(),   # ingested_at
                action,                 # action
                actor,                  # actor
                rng.randint(1_000_000, 9_999_999),  # actor_id
                False,                  # actor_is_bot
                org,                    # org
                rng.randint(100_000, 999_999),       # org_id
                repo or "",             # repo (empty string → NULL via COPY)
                "",                     # repo_id
                "",                     # business
                "",                     # business_id
                source_ip,              # source_ip
                "",                     # user_agent
                country,                # geo_country_code
                "",                     # geo_city
                "",                     # geo_latitude
                "",                     # geo_longitude
                "",                     # geo_is_proxy
                data_payload,           # data
                "hec",                   # ingestion_source
                f"{DEMO_SOURCE_FILE_PREFIX}{worker_id}/{event_ts.strftime('%Y/%m/%d')}/events.json.gz",
            ])

        current += one_hour

    buf.seek(0)
    return buf


def _copy_worker(args: dict[str, Any]) -> tuple[int, float]:
    """Worker function for multiprocessing.Pool.

    Generates events for a time window and COPYs them into the events table.
    Returns (rows_written, elapsed_seconds).
    """
    database_url: str = args["database_url"]
    org_logins: list[str] = args["org_logins"]
    repo_names_by_org: dict[str, list[str]] = args["repo_names_by_org"]
    logins: list[str] = args["logins"]
    start_dt: datetime = args["start_dt"]
    end_dt: datetime = args["end_dt"]
    seed: int = args["seed"]
    worker_id: int = args["worker_id"]
    n_days_total: int = args["n_days_total"]

    t0 = time.monotonic()
    conn = get_connection(database_url)
    cur = conn.cursor()

    # Generate CSV in memory and stream via COPY
    # For very large windows, generate day-by-day to bound memory usage
    one_day = timedelta(days=1)
    rows_written = 0
    day_start = start_dt

    while day_start < end_dt:
        day_end = min(day_start + one_day, end_dt)
        buf = _generate_event_csv_chunk(
            org_logins=org_logins,
            repo_names_by_org=repo_names_by_org,
            logins=logins,
            start_dt=day_start,
            end_dt=day_end,
            seed=seed,
            worker_id=worker_id,
            n_days_total=n_days_total,
        )

        # Count rows written (CSV lines)
        content = buf.getvalue()
        n_rows = content.count("\n")

        buf.seek(0)
        cur.copy_expert(
            """
            COPY events (
                document_id, created_at, ingested_at, action,
                actor, actor_id, actor_is_bot,
                org, org_id, repo, repo_id, business, business_id,
                source_ip, user_agent,
                geo_country_code, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                data, ingestion_source, source_file_path
            )
            FROM STDIN
            WITH (FORMAT csv, NULL '')
            """,
            buf,
        )
        conn.commit()
        rows_written += n_rows
        day_start = day_end

    cur.close()
    conn.close()
    return rows_written, time.monotonic() - t0


def seed_events(
    database_url: str,
    rng: random.Random,
    orgs: list[dict[str, Any]],
    logins: list[str],
    n_days: int,
    seed: int,
    workers: int,
    start_dt: datetime,
) -> None:
    """Seed the events hypertable using psycopg2 COPY FROM STDIN.

    Splits the time window across `workers` processes.
    """
    print(f"\n[6/7] Seeding audit events ({n_days} days, {workers} workers)...")
    print("       This is the largest phase — please wait.")

    conn = get_connection(database_url)
    cur = conn.cursor()

    # Clean up any existing demo-seeded events (safe re-run)
    print("  Cleaning up existing demo events...")
    cur.execute(
        f"DELETE FROM events WHERE source_file_path LIKE '{DEMO_SOURCE_FILE_PREFIX}%'"
    )
    conn.commit()
    cur.close()
    conn.close()

    # Build repo lookup for event generation (org → [repo_name, ...])
    conn2 = get_connection(database_url)
    cur2 = conn2.cursor()
    cur2.execute("SELECT org, repo_name FROM repositories LIMIT 500000")
    repo_rows = cur2.fetchall()
    cur2.close()
    conn2.close()

    repo_names_by_org: dict[str, list[str]] = {}
    for org_slug, repo_name in repo_rows:
        repo_names_by_org.setdefault(org_slug, []).append(repo_name)

    org_logins = [o["org_login"] for o in orgs]
    end_dt = start_dt + timedelta(days=n_days)

    # Split time window across workers
    window_seconds = int((end_dt - start_dt).total_seconds())
    chunk_seconds = window_seconds // workers
    worker_args = []
    for i in range(workers):
        w_start = start_dt + timedelta(seconds=i * chunk_seconds)
        w_end = (
            start_dt + timedelta(seconds=(i + 1) * chunk_seconds)
            if i < workers - 1
            else end_dt
        )
        worker_args.append({
            "database_url": database_url,
            "org_logins": org_logins,
            "repo_names_by_org": repo_names_by_org,
            "logins": logins,
            "start_dt": w_start,
            "end_dt": w_end,
            "seed": seed,
            "worker_id": i,
            "n_days_total": n_days,
        })

    if workers == 1:
        rows, elapsed = _copy_worker(worker_args[0])
        print(f"  ✓ Inserted ~{rows:,} event rows in {elapsed:.1f}s")
    else:
        with multiprocessing.Pool(processes=workers) as pool:
            results = pool.map(_copy_worker, worker_args)
        total_rows = sum(r for r, _ in results)
        max_elapsed = max(e for _, e in results)
        print(f"  ✓ Inserted ~{total_rows:,} event rows in {max_elapsed:.1f}s ({workers} workers)")


# ---------------------------------------------------------------------------
# Phase 7: Seed bot / integration events (COPY protocol)
# ---------------------------------------------------------------------------

def seed_bot_events(
    conn: "psycopg2.connection",
    args: argparse.Namespace,
    rng: random.Random,
    fake: "Faker",
    org_ids: list[int],
    repo_ids: list[int],
) -> None:
    """Seed integration bot audit events using psycopg2 COPY FROM STDIN.

    Bots generate a flat, sustained event rate (no weekday/weekend variation).
    Total rows = int(args.bot_eps * 86400 * args.days).
    """
    total_rows = int(args.bot_eps * 86400 * args.days)
    print(
        f"\n[7/7] Seeding {args.integration_bots} integration bots at {args.bot_eps} eps "
        f"({total_rows:,} total bot events)..."
    )
    print("       This phase uses flat-rate generation — bots don't sleep.")

    # Build a pool of bot login names
    suffixes = ["app", "bot", "sync", "integration"]
    bot_logins: list[str] = []
    seen_bot_logins: set[str] = set()
    for _ in range(args.integration_bots):
        login = f"{fake.word()}-{rng.choice(suffixes)}[bot]"
        # Ensure uniqueness
        base = login
        counter = 1
        while login in seen_bot_logins:
            login = f"{base[:-5]}-{counter}[bot]"
            counter += 1
        seen_bot_logins.add(login)
        bot_logins.append(login)

    # Resolve org logins from the IDs we were given
    cur = conn.cursor()
    cur.execute(
        "SELECT org_id, org_login FROM enterprise_orgs WHERE org_id = ANY(%s)",
        (org_ids,),
    )
    org_id_to_login: dict[int, str] = {row[0]: row[1] for row in cur.fetchall()}
    org_logins = [org_id_to_login.get(oid, f"org-{oid}") for oid in org_ids]

    # Build repo lookup (org → [repo_name, ...]) — reuse existing data
    cur.execute("SELECT org, repo_name FROM repositories LIMIT 500000")
    repo_rows = cur.fetchall()
    repo_names_by_org: dict[str, list[str]] = {}
    for org_slug, repo_name in repo_rows:
        repo_names_by_org.setdefault(org_slug, []).append(repo_name)

    country_codes = [c for c, _ in GEO_COUNTRIES]
    country_weights = [w for _, w in GEO_COUNTRIES]

    # Date window matching the rest of the seed run
    end_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=args.days)

    # Events per day (flat — no diurnal variation for bots)
    events_per_day = int(args.bot_eps * 86400)

    total_inserted = 0
    t0 = time.monotonic()
    one_day = timedelta(days=1)
    day_start = start_dt

    while day_start < end_dt:
        day_end = min(day_start + one_day, end_dt)

        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

        for _ in range(events_per_day):
            event_ts = day_start + timedelta(seconds=rng.randint(0, 86399))
            org = rng.choice(org_logins)
            actor = rng.choice(bot_logins)
            action = rng.choices(_BOT_ACTION_NAMES, weights=_BOT_ACTION_WEIGHTS, k=1)[0]

            repos = repo_names_by_org.get(org, [])
            repo = (
                rng.choice(repos)
                if repos and ("repo" in action or "deployment" in action or "check" in action)
                else None
            )

            country = rng.choices(country_codes, weights=country_weights, k=1)[0]
            source_ip = (
                f"{rng.randint(1, 223)}.{rng.randint(0, 255)}"
                f".{rng.randint(0, 255)}.{rng.randint(1, 254)}"
            )
            document_id = str(uuid.UUID(int=rng.getrandbits(128)))

            data_payload = json.dumps({
                "action": action,
                "@timestamp": event_ts.isoformat(),
                "actor": actor,
                "org": org,
                **({"repo": repo} if repo else {}),
            })

            writer.writerow([
                document_id,            # document_id
                event_ts.isoformat(),   # created_at
                event_ts.isoformat(),   # ingested_at
                action,                 # action
                actor,                  # actor
                rng.randint(1_000_000, 9_999_999),  # actor_id
                True,                   # actor_is_bot
                org,                    # org
                rng.randint(100_000, 999_999),       # org_id
                repo or "",             # repo (empty string → NULL via COPY)
                "",                     # repo_id
                "",                     # business
                "",                     # business_id
                source_ip,              # source_ip
                "",                     # user_agent
                country,                # geo_country_code
                "",                     # geo_city
                "",                     # geo_latitude
                "",                     # geo_longitude
                "",                     # geo_is_proxy
                data_payload,           # data
                "hec",                   # ingestion_source
                f"{DEMO_SOURCE_FILE_PREFIX}bots/{event_ts.strftime('%Y/%m/%d')}/bot-events.json.gz",
            ])

        content = buf.getvalue()
        n_rows = content.count("\n")
        buf.seek(0)

        cur.copy_expert(
            """
            COPY events (
                document_id, created_at, ingested_at, action,
                actor, actor_id, actor_is_bot,
                org, org_id, repo, repo_id, business, business_id,
                source_ip, user_agent,
                geo_country_code, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                data, ingestion_source, source_file_path
            )
            FROM STDIN
            WITH (FORMAT csv, NULL '')
            """,
            buf,
        )
        conn.commit()
        total_inserted += n_rows
        day_start = day_end

    cur.close()
    elapsed = time.monotonic() - t0
    print(
        f"  ✓ Inserted ~{total_inserted:,} bot event rows in {elapsed:.1f}s "
        f"({args.integration_bots} bots, {args.bot_eps} eps)"
    )


# ---------------------------------------------------------------------------
# Volume estimation (dry run)
# ---------------------------------------------------------------------------

def print_volume_estimates(args: argparse.Namespace) -> None:
    """Print estimated row counts and storage without writing anything."""
    n_weekdays = args.days * 5 // 7
    n_weekends = args.days - n_weekdays
    active_rate = 0.70
    weekday_events = args.users * active_rate * 50 * n_weekdays
    weekend_events = args.users * active_rate * 5 * n_weekends
    total_events = weekday_events + weekend_events

    # Bot events (flat rate — no weekday/weekend variation)
    bot_events = int(args.bot_eps * 86400 * args.days) if args.bot_eps > 0 else 0
    total_events_all = int(total_events) + bot_events

    copilot_metrics = args.orgs * args.days * 13  # ~13 combos per org per day
    copilot_seats = int(args.users * 0.70 * (args.days / 7))  # weekly snapshots

    print("\n=== DRY RUN: Volume Estimates ===")
    print(f"  Organizations:         {args.orgs:>12,}")
    print(f"  Users:                 {args.users:>12,}")
    print(f"  Repositories:          {args.repos:>12,}")
    print(f"  Days of history:       {args.days:>12,}")
    if args.integration_bots > 0:
        print(f"  Integration bots:      {args.integration_bots:>12,}")
        print(f"  Bot EPS:               {args.bot_eps:>12.1f}")
    print()
    print(f"  Human audit events:    {int(total_events):>12,}  (~{total_events/1e6:.1f}M rows)")
    if bot_events > 0:
        print(f"  Bot/integration events:{bot_events:>12,}  (~{bot_events/1e9:.2f}B rows)")
    print(f"  Total audit events:    {total_events_all:>12,}  (~{total_events_all/1e9:.2f}B rows)")
    print(f"  Copilot metrics:       {copilot_metrics:>12,}")
    print(f"  Copilot seat snaps:    {copilot_seats:>12,}")
    print()
    effective_eps = total_events_all / (args.days * 86400)
    print(f"  Effective avg ingest:  {effective_eps:>11.1f} eps")
    if args.bot_eps > 0:
        print(f"    └─ human:            {total_events/(args.days*86400):>11.1f} eps")
        print(f"    └─ bots:             {args.bot_eps:>11.1f} eps")
    print()
    raw_gb = total_events_all * 500 / 1e9
    compressed_gb = raw_gb / 10
    print(f"  Est. raw events size:  {raw_gb:>11.1f} GB")
    print(f"  Est. compressed size:  {compressed_gb:>11.1f} GB (with TimescaleDB ~10× compression)")
    print(f"  TimescaleDB chunks:    {math.ceil(args.days / 7):>12}  (1-week intervals)")
    print()
    print("Run without --dry-run to write data to the database.")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # Apply scale preset BEFORE dry-run check so estimates reflect the preset
    if args.scale:
        preset = SCALE_PRESETS[args.scale]
        args.orgs = preset["orgs"]
        args.users = preset["users"]
        args.repos = preset["repos"]
        args.days = preset["days"]
        args.integration_bots = preset["integration_bots"]
        args.bot_eps = preset["bot_eps"]
        print(f"  Applying --scale {args.scale} preset: {preset}")

    if args.dry_run:
        print_volume_estimates(args)
        return

    if not args.database_url:
        sys.exit(
            "DATABASE_URL is not set.\n"
            "Export it or pass --database-url.\n"
            "Example: export DATABASE_URL=postgresql://appuser:PASSWORD@localhost:5432/audit_logs"
        )

    # Initialise deterministic random sources
    rng = random.Random(args.seed)
    fake = Faker()
    fake.seed_instance(args.seed)

    # Date window: ends now, starts `days` ago
    end_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=args.days)
    start_date = start_dt.date()

    print(f"OctoWatch Demo Seeder  (seed={args.seed})")
    print(f"  Date window: {start_date} → {end_dt.date()}")
    print(f"  Orgs={args.orgs}  Users={args.users}  Repos={args.repos}  Days={args.days}")
    if args.integration_bots > 0:
        print(f"  Bots={args.integration_bots}  BotEPS={args.bot_eps}")
    print(f"  Workers={args.workers}  BatchSize={args.batch_size}")

    checkpoint = load_checkpoint(args.seed)

    # ------------------------------------------------------------------
    # Phase 1: Orgs
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "orgs", args.resume):
        print("\n[1/7] Skipping organizations (already done)")
        # Reload org data from DB for downstream phases
        conn_tmp = get_connection(args.database_url)
        cur_tmp = conn_tmp.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur_tmp.execute("SELECT org_login, org_id, member_count FROM enterprise_orgs")
        orgs = [dict(r) for r in cur_tmp.fetchall()]
        cur_tmp.close()
        conn_tmp.close()
    else:
        mark_phase(checkpoint, "orgs", "in_progress")
        conn = get_connection(args.database_url)
        try:
            orgs = seed_orgs(conn, fake, rng, args.orgs, args.users, args.batch_size)
        finally:
            conn.close()
        mark_phase(checkpoint, "orgs", "done")

    # ------------------------------------------------------------------
    # Phase 2: Users
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "users", args.resume):
        print("\n[2/7] Skipping users (already done)")
        conn_tmp = get_connection(args.database_url)
        cur_tmp = conn_tmp.cursor()
        cur_tmp.execute("SELECT DISTINCT github_login FROM org_members LIMIT %s", (args.users * 2,))
        logins = [r[0] for r in cur_tmp.fetchall()]
        cur_tmp.close()
        conn_tmp.close()
    else:
        mark_phase(checkpoint, "users", "in_progress")
        conn = get_connection(args.database_url)
        try:
            logins = seed_users(conn, fake, rng, orgs, args.users, args.batch_size)
        finally:
            conn.close()
        mark_phase(checkpoint, "users", "done")

    # ------------------------------------------------------------------
    # Phase 3: Repositories
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "repos", args.resume):
        print("\n[3/7] Skipping repositories (already done)")
    else:
        mark_phase(checkpoint, "repos", "in_progress")
        conn = get_connection(args.database_url)
        try:
            seed_repos(conn, fake, rng, orgs, args.repos, args.batch_size)
        finally:
            conn.close()
        mark_phase(checkpoint, "repos", "done")

    if args.skip_events:
        print("\n--skip-events set: skipping Copilot metrics and audit events.")
        print("Reference data seeding complete.")
        return

    # ------------------------------------------------------------------
    # Phase 4: Copilot seat snapshots
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "copilot_seats", args.resume):
        print("\n[4/7] Skipping Copilot seat snapshots (already done)")
    else:
        mark_phase(checkpoint, "copilot_seats", "in_progress")
        conn = get_connection(args.database_url)
        try:
            seed_copilot_seats(conn, rng, orgs, logins, args.days, args.batch_size, start_date)
        finally:
            conn.close()
        mark_phase(checkpoint, "copilot_seats", "done")

    # ------------------------------------------------------------------
    # Phase 5: Copilot daily metrics
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "copilot_metrics", args.resume):
        print("\n[5/7] Skipping Copilot daily metrics (already done)")
    else:
        mark_phase(checkpoint, "copilot_metrics", "in_progress")
        conn = get_connection(args.database_url)
        try:
            seed_copilot_metrics(conn, rng, orgs, args.days, args.batch_size, start_date)
        finally:
            conn.close()
        mark_phase(checkpoint, "copilot_metrics", "done")

    # ------------------------------------------------------------------
    # Phase 6: Audit events (COPY protocol, parallel)
    # ------------------------------------------------------------------
    if should_skip(checkpoint, "events", args.resume):
        print("\n[6/7] Skipping audit events (already done)")
    else:
        mark_phase(checkpoint, "events", "in_progress")
        seed_events(
            args.database_url,
            rng,
            orgs,
            logins,
            args.days,
            args.seed,
            args.workers,
            start_dt,
        )
        mark_phase(checkpoint, "events", "done")

    # ------------------------------------------------------------------
    # Phase 7: Bot / integration events (COPY protocol)
    # ------------------------------------------------------------------
    if args.integration_bots > 0 and args.bot_eps > 0:
        if not should_skip(checkpoint, "bot_events", args.resume):
            mark_phase(checkpoint, "bot_events", "in_progress")
            org_ids = [o["org_id"] for o in orgs]
            conn = get_connection(args.database_url)
            try:
                seed_bot_events(conn, args, rng, fake, org_ids, [])
            finally:
                conn.close()
            mark_phase(checkpoint, "bot_events", "done")
            save_checkpoint(checkpoint)
        else:
            print("\n[7/7] Skipping bot events (already done)")
    else:
        print("\n[7/7] Skipping bot events (--integration-bots not set)")

    print("\n✓ All phases complete!")
    print(f"  Checkpoint saved to {CHECKPOINT_FILE}")
    print("  Run with --dry-run to see volume estimates for different scale parameters.")


if __name__ == "__main__":
    main()
