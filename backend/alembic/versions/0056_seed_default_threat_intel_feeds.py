"""Seed default threat intelligence feeds.

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-01 00:00:00.000000+00:00

Adds an ``is_default`` boolean column to ``threat_intel_feeds`` and inserts
five curated, open-source threat intelligence feeds so new installations
see value on first load.  The migration is idempotent — feeds are matched
by URL using ``ON CONFLICT`` so re-running is safe for existing installs.
"""

import sqlalchemy as sa

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

# (name, url, feed_type, refresh_interval_minutes, description)
_DEFAULT_FEEDS = [
    (
        "Abuse.ch URLhaus",
        "https://urlhaus.abuse.ch/downloads/csv_recent/",
        "domain",
        360,
        "Malicious URLs used for malware distribution, updated frequently by abuse.ch.",
    ),
    (
        "Abuse.ch Feodo Tracker",
        "https://feodotracker.abuse.ch/downloads/ipblocklist_recommended.txt",
        "ip",
        360,
        "Botnet command-and-control server IPs tracked by Feodo Tracker.",
    ),
    (
        "AlienVault OTX",
        "https://otx.alienvault.com/api/v1/pulses/subscribed",
        "domain",
        1440,
        "Community-sourced indicators from AlienVault Open Threat Exchange.",
    ),
    (
        "CISA Known Exploited Vulnerabilities",
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "domain",
        1440,
        "Actively exploited CVEs catalogued by CISA — critical for patch prioritisation.",
    ),
    (
        "PhishTank",
        "https://data.phishtank.com/data/online-valid.csv",
        "domain",
        720,
        "Verified phishing URLs submitted and validated by the PhishTank community.",
    ),
]


def upgrade() -> None:
    """Add is_default column and seed default threat intel feeds."""
    # 1. Add the is_default column (FALSE for any pre-existing rows).
    op.add_column(
        "threat_intel_feeds",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )

    # 2. Add a unique constraint on url to support idempotent upserts.
    op.create_unique_constraint(
        "uq_threat_intel_feeds_url",
        "threat_intel_feeds",
        ["url"],
    )

    # 3. Seed the five default feeds.
    conn = op.get_bind()
    for name, url, feed_type, refresh_minutes, _description in _DEFAULT_FEEDS:
        conn.execute(
            sa.text(
                "INSERT INTO threat_intel_feeds"
                "    (name, url, feed_type, refresh_interval_minutes,"
                "     enabled, is_default, created_by)"
                " VALUES"
                "    (:name, :url, :feed_type, :refresh_minutes,"
                "     TRUE, TRUE, 'system')"
                " ON CONFLICT (url) DO UPDATE SET"
                "    name = EXCLUDED.name,"
                "    feed_type = EXCLUDED.feed_type,"
                "    refresh_interval_minutes = EXCLUDED.refresh_interval_minutes,"
                "    is_default = TRUE,"
                "    updated_at = NOW()"
            ),
            {
                "name": name,
                "url": url,
                "feed_type": feed_type,
                "refresh_minutes": refresh_minutes,
            },
        )


def downgrade() -> None:
    """Remove seeded default feeds, drop unique constraint, and remove is_default column."""
    conn = op.get_bind()
    urls = [url for _, url, *_ in _DEFAULT_FEEDS]
    conn.execute(
        sa.text("DELETE FROM threat_intel_feeds WHERE url = ANY(:urls) AND is_default = TRUE"),
        {"urls": urls},
    )
    op.drop_constraint("uq_threat_intel_feeds_url", "threat_intel_feeds", type_="unique")
    op.drop_column("threat_intel_feeds", "is_default")
