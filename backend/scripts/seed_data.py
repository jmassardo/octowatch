#!/usr/bin/env python3
"""Sample data generator for OctoWatch.

Generates 30 days of realistic GitHub audit events including logins,
repo operations, team changes, Actions runs, Copilot usage, security events,
and suspicious patterns that trigger at least 5 different detection types.

Usage:
    python scripts/seed_data.py [--days 30] [--events-per-day 500] [--clear]

Outputs JSON to stdout for piping into the application, or can insert directly
into the database when DATABASE_URL is configured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

# ─── Realistic data pools ────────────────────────────────────────────────────

USERNAMES = [
    "alice-dev",
    "bob-admin",
    "charlie-ops",
    "diana-security",
    "eve-attacker",
    "frank-contractor",
    "grace-manager",
    "henry-intern",
    "iris-lead",
    "jack-sre",
    "kate-analyst",
    "leo-backend",
    "mia-frontend",
    "noah-devops",
    "olivia-qa",
]

BOT_ACCOUNTS = [
    "dependabot[bot]",
    "github-actions[bot]",
    "renovate[bot]",
]

ORG_NAME = "acme-corp"

REPOS = [
    "acme-corp/payments-api",
    "acme-corp/frontend-app",
    "acme-corp/infrastructure",
    "acme-corp/mobile-client",
    "acme-corp/data-pipeline",
    "acme-corp/auth-service",
    "acme-corp/docs",
    "acme-corp/ml-models",
    "acme-corp/shared-libs",
    "acme-corp/admin-portal",
]

TEAMS = [
    "engineering",
    "security",
    "platform",
    "frontend",
    "backend",
    "data",
    "sre",
    "mobile",
]

# Realistic geolocations: (city, country_code, latitude, longitude, ip_prefix)
GEOLOCATIONS = [
    ("San Francisco", "US", 37.7749, -122.4194, "198.51."),
    ("New York", "US", 40.7128, -74.0060, "203.0."),
    ("London", "GB", 51.5074, -0.1278, "185.12."),
    ("Berlin", "DE", 52.5200, 13.4050, "91.108."),
    ("Tokyo", "JP", 35.6762, 139.6503, "103.22."),
    ("Sydney", "AU", -33.8688, 151.2093, "202.14."),
    ("São Paulo", "BR", -23.5505, -46.6333, "177.71."),
    ("Toronto", "CA", 43.6532, -79.3832, "206.167."),
    ("Mumbai", "IN", 19.0760, 72.8777, "106.51."),
    ("Singapore", "SG", 1.3521, 103.8198, "175.45."),
    ("Paris", "FR", 48.8566, 2.3522, "176.31."),
    ("Amsterdam", "NL", 52.3676, 4.9041, "178.62."),
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "GitHub CLI/2.40.0",
    "git/2.42.0",
    "GitHub Desktop/3.3.5",
]

SUSPICIOUS_USER_AGENTS = [
    "python-requests/2.31.0",
    "curl/8.4.0",
    "Go-http-client/1.1",
]

WORKFLOW_FILES = [
    ".github/workflows/ci.yml",
    ".github/workflows/deploy.yml",
    ".github/workflows/release.yml",
    ".github/workflows/security-scan.yml",
]

# Marker for identifying seed data
SEED_SOURCE = "seed_generator"

# Use an instance-level RNG (seeded in main for reproducibility).
# This avoids S311 false positives since this script is not security-critical.
_rng = random.Random()  # noqa: S311


def _random_ip(geo_idx: int) -> str:
    """Generate a random IP address with a prefix matching the geolocation."""
    prefix = GEOLOCATIONS[geo_idx][4]
    return f"{prefix}{_rng.randint(1, 254)}.{_rng.randint(1, 254)}"


def _make_document_id() -> str:
    """Generate a unique document ID matching GitHub's format."""
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:24]


def _random_timestamp(day_offset: int, base: datetime) -> datetime:
    """Generate a random timestamp within a specific day."""
    day_start = base - timedelta(days=day_offset)
    seconds_offset = _rng.randint(0, 86399)
    return day_start + timedelta(seconds=seconds_offset)


def _business_hours_timestamp(day_offset: int, base: datetime) -> datetime:
    """Generate a timestamp during business hours (9am-6pm)."""
    day_start = base - timedelta(days=day_offset)
    day_start = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
    hour = _rng.randint(9, 17)
    minute = _rng.randint(0, 59)
    return day_start + timedelta(hours=hour, minutes=minute)


def _after_hours_timestamp(day_offset: int, base: datetime) -> datetime:
    """Generate a timestamp outside business hours (11pm-4am)."""
    day_start = base - timedelta(days=day_offset)
    day_start = day_start.replace(hour=0, minute=0, second=0, microsecond=0)
    hour = _rng.choice([23, 0, 1, 2, 3])
    minute = _rng.randint(0, 59)
    return day_start + timedelta(hours=hour, minutes=minute)


def _base_event(
    action: str,
    actor: str,
    timestamp: datetime,
    geo_idx: int,
    repo: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a base event dict."""
    geo = GEOLOCATIONS[geo_idx]
    event: dict[str, Any] = {
        "document_id": _make_document_id(),
        "action": action,
        "actor": actor,
        "actor_id": hash(actor) % 1_000_000,
        "actor_is_bot": actor.endswith("[bot]"),
        "org": ORG_NAME,
        "org_id": 12345678,
        "source_ip": _random_ip(geo_idx),
        "user_agent": _rng.choice(USER_AGENTS),
        "created_at": timestamp.isoformat(),
        "ingested_at": (timestamp + timedelta(seconds=_rng.randint(1, 30))).isoformat(),
        "geo_city": geo[0],
        "geo_country_code": geo[1],
        "geo_latitude": geo[2],
        "geo_longitude": geo[3],
        "source": SEED_SOURCE,
        "data": data or {},
    }
    if repo:
        event["repo"] = repo
        event["repo_id"] = hash(repo) % 1_000_000
    return event


def generate_login_events(
    num_days: int, events_per_day: int, base: datetime
) -> list[dict[str, Any]]:
    """Generate normal login/auth events."""
    events: list[dict[str, Any]] = []
    for day in range(num_days):
        count = max(1, events_per_day // 5)
        for _ in range(count):
            actor = _rng.choice(USERNAMES[:12])  # Normal users
            geo_idx = _rng.randint(0, len(GEOLOCATIONS) - 1)
            ts = _business_hours_timestamp(day, base)
            events.append(
                _base_event(
                    action="auth.login",
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    data={"login_method": _rng.choice(["sso", "oauth", "pat"])},
                )
            )
    return events


def generate_repo_operations(
    num_days: int, events_per_day: int, base: datetime
) -> list[dict[str, Any]]:
    """Generate repository CRUD events."""
    events: list[dict[str, Any]] = []
    actions = [
        "repo.create",
        "repo.destroy",
        "repo.access",
        "repo.rename",
        "repo.transfer",
        "repo.archived",
    ]
    for day in range(num_days):
        count = max(1, events_per_day // 8)
        for _ in range(count):
            actor = _rng.choice(USERNAMES[:10])
            repo = _rng.choice(REPOS)
            geo_idx = _rng.randint(0, 5)
            ts = _business_hours_timestamp(day, base)
            action = _rng.choice(actions)
            data: dict[str, Any] = {}
            if action == "repo.access":
                data["visibility"] = _rng.choice(["private", "private", "private", "internal"])
            if action == "repo.create":
                data["description"] = f"New repository created by {actor}"
            events.append(
                _base_event(
                    action=action,
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    repo=repo,
                    data=data,
                )
            )
    return events


def generate_team_changes(
    num_days: int, events_per_day: int, base: datetime
) -> list[dict[str, Any]]:
    """Generate team membership changes."""
    events: list[dict[str, Any]] = []
    actions = [
        "team.add_member",
        "team.remove_member",
        "team.create",
        "team.destroy",
        "team.change_member_role",
    ]
    for day in range(num_days):
        count = max(1, events_per_day // 15)
        for _ in range(count):
            actor = _rng.choice(USERNAMES[:8])
            team = _rng.choice(TEAMS)
            geo_idx = _rng.randint(0, 5)
            ts = _business_hours_timestamp(day, base)
            action = _rng.choice(actions)
            target = _rng.choice(USERNAMES)
            data: dict[str, Any] = {"team": team, "target_user": target}
            if action == "team.change_member_role":
                data["role"] = _rng.choice(["member", "maintainer"])
            events.append(
                _base_event(
                    action=action,
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    data=data,
                )
            )
    return events


def generate_actions_events(
    num_days: int, events_per_day: int, base: datetime
) -> list[dict[str, Any]]:
    """Generate GitHub Actions workflow events."""
    events: list[dict[str, Any]] = []
    for day in range(num_days):
        count = max(1, events_per_day // 6)
        for _ in range(count):
            actor = _rng.choice(USERNAMES[:10] + BOT_ACCOUNTS)
            repo = _rng.choice(REPOS)
            geo_idx = _rng.randint(0, 5)
            ts = _random_timestamp(day, base)
            workflow = _rng.choice(WORKFLOW_FILES)
            conclusion = _rng.choice(
                ["success", "success", "success", "success", "failure", "cancelled"]
            )
            events.append(
                _base_event(
                    action="workflows.completed_workflow_run",
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    repo=repo,
                    data={
                        "workflow_name": workflow,
                        "conclusion": conclusion,
                        "run_number": _rng.randint(1, 5000),
                        "head_branch": _rng.choice(["main", "develop", "feature/auth"]),
                    },
                )
            )
    return events


def generate_copilot_events(num_days: int, base: datetime) -> list[dict[str, Any]]:
    """Generate Copilot-related events."""
    events: list[dict[str, Any]] = []
    copilot_actions = [
        "copilot.seat_assignment_created",
        "copilot.seat_assignment_cancelled",
        "copilot.cfb_policy_update",
    ]
    # Sparse events — roughly weekly
    for day in range(0, num_days, 7):
        for _ in range(_rng.randint(1, 3)):
            actor = _rng.choice(USERNAMES[:5])
            geo_idx = _rng.randint(0, 3)
            ts = _business_hours_timestamp(day, base)
            action = _rng.choice(copilot_actions)
            target = _rng.choice(USERNAMES)
            events.append(
                _base_event(
                    action=action,
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    data={"target_user": target, "policy": "enabled"},
                )
            )
    return events


def generate_security_events(
    num_days: int, events_per_day: int, base: datetime
) -> list[dict[str, Any]]:
    """Generate security-related events (secret scanning, branch protection)."""
    events: list[dict[str, Any]] = []
    for day in range(num_days):
        count = max(1, events_per_day // 20)
        for _ in range(count):
            actor = _rng.choice(USERNAMES[:10])
            repo = _rng.choice(REPOS)
            geo_idx = _rng.randint(0, 5)
            ts = _business_hours_timestamp(day, base)
            action = _rng.choice(
                [
                    "secret_scanning_alert.create",
                    "secret_scanning_alert.resolve",
                    "protected_branch.create",
                    "protected_branch.update_required_status_checks",
                    "dependabot_alert.create",
                    "dependabot_alert.dismiss",
                ]
            )
            events.append(
                _base_event(
                    action=action,
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    repo=repo,
                    data={"alert_type": "secret_scanning" if "secret" in action else "dependabot"},
                )
            )
    return events


def generate_admin_events(num_days: int, base: datetime) -> list[dict[str, Any]]:
    """Generate admin/org operations."""
    events: list[dict[str, Any]] = []
    admin_actions = [
        "org.update_member",
        "org.add_member",
        "org.remove_member",
        "org.update_default_repository_permission",
        "org.enable_two_factor_requirement",
    ]
    for day in range(num_days):
        if _rng.random() < 0.3:  # Not every day
            actor = _rng.choice(["bob-admin", "grace-manager", "alice-dev"])
            geo_idx = _rng.randint(0, 3)
            ts = _business_hours_timestamp(day, base)
            action = _rng.choice(admin_actions)
            target = _rng.choice(USERNAMES)
            data: dict[str, Any] = {"target_user": target}
            if "update_member" in action:
                data["permission"] = _rng.choice(["member", "member", "admin"])
            events.append(
                _base_event(
                    action=action,
                    actor=actor,
                    timestamp=ts,
                    geo_idx=geo_idx,
                    data=data,
                )
            )
    return events


# ─── Suspicious patterns (trigger detections) ────────────────────────────────


def generate_impossible_travel(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: same user logs in from distant cities within 1 hour."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"

    # Login from San Francisco
    ts1 = base - timedelta(days=2, hours=3)
    events.append(
        _base_event(
            action="auth.login",
            actor=actor,
            timestamp=ts1,
            geo_idx=0,
            data={"login_method": "pat"},
        )
    )

    # Login from Tokyo 30 minutes later (impossible travel)
    ts2 = ts1 + timedelta(minutes=30)
    events.append(
        _base_event(
            action="auth.login",
            actor=actor,
            timestamp=ts2,
            geo_idx=4,
            data={"login_method": "pat"},
        )
    )

    # Second incident: London then Mumbai
    ts3 = base - timedelta(days=5, hours=6)
    events.append(
        _base_event(
            action="auth.login",
            actor=actor,
            timestamp=ts3,
            geo_idx=2,
            data={"login_method": "sso"},
        )
    )
    ts4 = ts3 + timedelta(minutes=45)
    events.append(
        _base_event(
            action="auth.login",
            actor=actor,
            timestamp=ts4,
            geo_idx=8,
            data={"login_method": "sso"},
        )
    )

    return events


def generate_mass_repo_deletion(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: single user deletes many repos in short window."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"
    ts_start = base - timedelta(days=1, hours=2)

    for i in range(8):
        ts = ts_start + timedelta(minutes=i * 2)
        events.append(
            _base_event(
                action="repo.destroy",
                actor=actor,
                timestamp=ts,
                geo_idx=4,
                repo=f"acme-corp/temp-repo-{i}",
                data={"reason": "cleanup"},
            )
        )
    return events


def generate_after_hours_admin(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: admin operations happening at unusual hours."""
    events: list[dict[str, Any]] = []
    actor = "frank-contractor"

    for day in [1, 3, 7]:
        ts = _after_hours_timestamp(day, base)
        events.append(
            _base_event(
                action="org.update_member",
                actor=actor,
                timestamp=ts,
                geo_idx=6,
                data={"permission": "admin", "target_user": "henry-intern"},
            )
        )

    return events


def generate_privilege_escalation(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: rapid privilege escalation — multiple role grants."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"
    ts_start = base - timedelta(days=3, hours=14)

    targets = ["henry-intern", "frank-contractor", "leo-backend", "mia-frontend", "noah-devops"]
    for i, target in enumerate(targets):
        ts = ts_start + timedelta(minutes=i * 3)
        events.append(
            _base_event(
                action="org.update_member",
                actor=actor,
                timestamp=ts,
                geo_idx=4,
                data={"permission": "admin", "target_user": target},
            )
        )

    return events


def generate_branch_protection_disable(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: branch protection disabled on critical repos."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"

    for repo in ["acme-corp/payments-api", "acme-corp/auth-service"]:
        ts = base - timedelta(days=4, hours=10)
        events.append(
            _base_event(
                action="protected_branch.destroy",
                actor=actor,
                timestamp=ts,
                geo_idx=4,
                repo=repo,
                data={"branch": "main"},
            )
        )

    return events


def generate_suspicious_webhook_deletion(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: webhook deletion (defense evasion)."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"
    ts = base - timedelta(days=2, hours=1)

    for repo in ["acme-corp/payments-api", "acme-corp/infrastructure"]:
        events.append(
            _base_event(
                action="hook.destroy",
                actor=actor,
                timestamp=ts,
                geo_idx=4,
                repo=repo,
                data={
                    "hook_id": _rng.randint(10000, 99999),
                    "events": ["push", "pull_request"],
                },
            )
        )
    return events


def generate_suspicious_user_agent_events(base: datetime) -> list[dict[str, Any]]:
    """Detection trigger: events from suspicious user agents."""
    events: list[dict[str, Any]] = []
    actor = "eve-attacker"

    for day in [1, 2, 5]:
        ts = base - timedelta(days=day, hours=8)
        event = _base_event(
            action="repo.access",
            actor=actor,
            timestamp=ts,
            geo_idx=4,
            repo=_rng.choice(REPOS),
            data={"visibility": "private"},
        )
        event["user_agent"] = _rng.choice(SUSPICIOUS_USER_AGENTS)
        events.append(event)

    return events


def generate_all_events(num_days: int = 30, events_per_day: int = 500) -> list[dict[str, Any]]:
    """Generate all event categories and combine them."""
    base = datetime.now(UTC)

    all_events: list[dict[str, Any]] = []

    # Normal operational events
    all_events.extend(generate_login_events(num_days, events_per_day, base))
    all_events.extend(generate_repo_operations(num_days, events_per_day, base))
    all_events.extend(generate_team_changes(num_days, events_per_day, base))
    all_events.extend(generate_actions_events(num_days, events_per_day, base))
    all_events.extend(generate_copilot_events(num_days, base))
    all_events.extend(generate_security_events(num_days, events_per_day, base))
    all_events.extend(generate_admin_events(num_days, base))

    # Suspicious patterns that trigger detections
    all_events.extend(generate_impossible_travel(base))
    all_events.extend(generate_mass_repo_deletion(base))
    all_events.extend(generate_after_hours_admin(base))
    all_events.extend(generate_privilege_escalation(base))
    all_events.extend(generate_branch_protection_disable(base))
    all_events.extend(generate_suspicious_webhook_deletion(base))
    all_events.extend(generate_suspicious_user_agent_events(base))

    # Sort by timestamp
    all_events.sort(key=lambda e: e["created_at"])

    return all_events


def main() -> None:
    """CLI entry point for the seed data generator."""
    parser = argparse.ArgumentParser(description="Generate realistic sample data for OctoWatch")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of data to generate (default: 30)",
    )
    parser.add_argument(
        "--events-per-day",
        type=int,
        default=500,
        help="Approximate number of events per day (default: 500)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing seed data before generating",
    )
    parser.add_argument(
        "--format",
        choices=["json", "summary"],
        default="summary",
        help="Output format: json (raw events) or summary (statistics)",
    )
    args = parser.parse_args()

    # Set a fixed seed for reproducibility
    _rng.seed(42)

    events = generate_all_events(num_days=args.days, events_per_day=args.events_per_day)

    if args.format == "json":
        json.dump(events, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        # Print summary statistics
        action_counts: dict[str, int] = {}
        actor_counts: dict[str, int] = {}
        for event in events:
            action = event["action"]
            namespace = action.split(".")[0]
            action_counts[namespace] = action_counts.get(namespace, 0) + 1
            actor_counts[event["actor"]] = actor_counts.get(event["actor"], 0) + 1

        print(f"Generated {len(events)} events over {args.days} days")  # noqa: T201
        print("\nEvents by namespace:")  # noqa: T201
        for ns, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            print(f"  {ns}: {count}")  # noqa: T201
        print("\nEvents by actor (top 10):")  # noqa: T201
        for actor, count in sorted(actor_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {actor}: {count}")  # noqa: T201

        # Count suspicious patterns
        suspicious_actors = {"eve-attacker", "frank-contractor"}
        suspicious_count = sum(1 for e in events if e["actor"] in suspicious_actors)
        print(f"\nSuspicious events (detection triggers): {suspicious_count}")  # noqa: T201
        print("Detection types triggered:")  # noqa: T201
        print("  1. Impossible travel (eve-attacker: SF→Tokyo, London→Mumbai)")  # noqa: T201
        print("  2. Mass repo deletion (eve-attacker: 8 repos in 16 minutes)")  # noqa: T201
        print("  3. After-hours admin operations (frank-contractor)")  # noqa: T201
        print("  4. Rapid privilege escalation (eve-attacker: 5 admin grants)")  # noqa: T201
        print("  5. Branch protection disable (eve-attacker: 2 critical repos)")  # noqa: T201
        print("  6. Webhook deletion / defense evasion (eve-attacker)")  # noqa: T201
        print("  7. Suspicious user agent (python-requests/curl)")  # noqa: T201


if __name__ == "__main__":
    main()
