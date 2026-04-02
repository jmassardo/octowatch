"""Shared rate limiter instance for per-endpoint rate limiting.

This module exists to avoid circular imports between ``app.main`` and
routers that need the ``limiter`` object for ``@limiter.limit()`` decorators.

The same ``Limiter`` instance is also stored on ``app.state.limiter`` by
``create_app()`` in ``app.main`` (required by the SlowAPI middleware), but
decorators need a module-level reference that can be imported at definition
time.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
