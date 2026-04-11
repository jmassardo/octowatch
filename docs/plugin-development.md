# Plugin Development Guide

OctoWatch supports custom enrichment plugins that run during event ingestion.
Plugins can add metadata, risk scores, threat-intelligence tags, or any other
contextual data to audit events.

## Architecture

```
Audit Event Ingested
        │
        ▼
  _normalize_event()
        │
        ▼
  PluginManager.run_enrichments(event)
        │
        ├── Plugin A → {"risk_score": 8.5}
        ├── Plugin B → {"geo_trust": "low"}
        └── Plugin C → None (skip)
        │
        ▼
  Merged into custom_enrichments JSONB column
```

## Creating a Plugin

### 1. Create a Python file

Place your plugin in `backend/app/plugins/`. The file name should be
descriptive (e.g. `my_enrichment.py`). Files starting with `_` are ignored.

### 2. Implement the EnrichmentPlugin interface

```python
from typing import Any
from app.plugins.base import EnrichmentPlugin


class MyEnrichmentPlugin(EnrichmentPlugin):
    """Short description of what this plugin does."""

    @property
    def name(self) -> str:
        return "my_enrichment"  # Unique name; used as key in custom_enrichments

    @property
    def version(self) -> str:
        return "1.0.0"

    def on_load(self) -> None:
        """Called once at startup. Open connections, load data, etc."""
        pass

    async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Called for every event. Return enrichment dict or None to skip."""
        source_ip = event.get("source_ip")
        if not source_ip:
            return None

        # Your enrichment logic here
        return {
            "risk_score": 5.0,
            "source": "my_service",
        }

    def on_unload(self) -> None:
        """Called at shutdown. Close connections, flush buffers, etc."""
        pass
```

### 3. Available event fields

The `event` dict passed to `enrich()` contains:

| Field | Type | Description |
|-------|------|-------------|
| `action` | `str` | GitHub audit action (e.g. `org.update_member`) |
| `actor` | `str \| None` | GitHub username of the actor |
| `org` | `str \| None` | Organization name |
| `repo` | `str \| None` | Repository full name (org/repo) |
| `source_ip` | `str \| None` | Source IP address |
| `created_at` | `datetime` | Event timestamp |
| `data` | `dict` | Full event payload |
| `geo_country_code` | `str \| None` | GeoIP country code |
| `geo_city` | `str \| None` | GeoIP city |

### 4. Return value

Return a `dict[str, Any]` with your enrichment data, or `None` to skip the
event. The returned dict is stored under your plugin's `name` key in the
event's `custom_enrichments` JSONB column:

```json
{
  "my_enrichment": {
    "risk_score": 5.0,
    "source": "my_service"
  },
  "another_plugin": {
    "tags": ["internal", "trusted"]
  }
}
```

## Error Isolation

Plugin exceptions are **fully isolated**. If your plugin raises an exception:

- The error is logged with full traceback
- The event is still ingested without your enrichment
- Other plugins continue to run
- Core ingestion is never blocked

This means you can safely make external API calls, database queries, etc.
without risking ingestion pipeline reliability.

## Lifecycle

| Hook | When | Use for |
|------|------|---------|
| `on_load()` | Startup, after instantiation | Open connections, warm caches |
| `enrich(event)` | Every ingested event | Core enrichment logic |
| `on_unload()` | Graceful shutdown | Close connections, flush buffers |

## Example: IP Reputation Plugin

See `backend/app/plugins/example_ip_reputation.py` for a complete example
that checks source IPs against a known-bad list.

## Best Practices

1. **Keep `enrich()` fast** — it runs for every event. Cache external lookups.
2. **Use `on_load()` for setup** — don't initialise resources in `enrich()`.
3. **Return `None` early** — skip events that don't need enrichment.
4. **Be defensive** — check for `None` values, handle missing fields.
5. **Log sparingly** — use `structlog.get_logger()` but avoid per-event logging.
6. **Thread-safety** — `enrich()` may be called concurrently.

## Testing Your Plugin

```python
import pytest
from my_plugin import MyEnrichmentPlugin


@pytest.mark.asyncio
async def test_enrich_with_ip():
    plugin = MyEnrichmentPlugin()
    plugin.on_load()

    result = await plugin.enrich({
        "action": "auth.login",
        "source_ip": "1.2.3.4",
        "actor": "testuser",
    })

    assert result is not None
    assert "risk_score" in result


@pytest.mark.asyncio
async def test_enrich_skips_without_ip():
    plugin = MyEnrichmentPlugin()
    plugin.on_load()

    result = await plugin.enrich({
        "action": "auth.login",
        "actor": "testuser",
    })

    assert result is None
```
