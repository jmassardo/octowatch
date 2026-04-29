"""Rule library router: browse and enable pre-built detection rule templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, get_valkey, require_permission, verify_csrf
from app.schemas.detection import RuleCreate, RuleResponse
from app.services import rule_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rules/library", tags=["rule-library"])

_LIBRARY_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "rule_library.json"


class LibraryRule(BaseModel):
    """Schema for a rule library entry (read-only template)."""

    name: str
    slug: str
    description: str
    category: str
    default_severity: str
    default_confidence: str = "medium"
    logic_type: str
    logic_config: dict[str, Any]


class LibraryCategory(BaseModel):
    """Group of rules within a category."""

    category: str
    display_name: str
    rules: list[LibraryRule]


class LibraryResponse(BaseModel):
    """Response containing all library rules grouped by category."""

    categories: list[LibraryCategory]
    total_rules: int


class EnableRequest(BaseModel):
    """Optional overrides when enabling a library rule."""

    severity: str | None = Field(None, pattern=r"^(critical|high|medium|low|info)$")
    confidence: str | None = Field(None, pattern=r"^(high|medium|low)$")
    enabled: bool = True


class CustomizeResponse(BaseModel):
    """Pre-filled rule creation payload for customization."""

    rule: RuleCreate


# ─── Category display names ──────────────────────────────────────────────────

_CATEGORY_DISPLAY: dict[str, str] = {
    "account_compromise": "Account Compromise",
    "privilege_escalation": "Privilege Escalation",
    "data_exfiltration": "Data Exfiltration",
    "supply_chain": "Supply Chain & CI/CD",
    "defense_evasion": "Defense Evasion",
}

# ─── Category ordering ───────────────────────────────────────────────────────

_CATEGORY_ORDER: list[str] = [
    "account_compromise",
    "privilege_escalation",
    "data_exfiltration",
    "supply_chain",
    "defense_evasion",
]


def _load_library() -> list[dict[str, Any]]:
    """Load the rule library from the JSON fixture file."""
    with open(_LIBRARY_PATH) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _group_by_category(rules: list[dict[str, Any]]) -> list[LibraryCategory]:
    """Group library rules by category with stable ordering."""
    buckets: dict[str, list[LibraryRule]] = {}
    for rule_data in rules:
        cat = rule_data.get("category", "other")
        if cat not in buckets:
            buckets[cat] = []
        buckets[cat].append(LibraryRule(**rule_data))

    categories: list[LibraryCategory] = []
    for cat_key in _CATEGORY_ORDER:
        if cat_key in buckets:
            categories.append(
                LibraryCategory(
                    category=cat_key,
                    display_name=_CATEGORY_DISPLAY.get(cat_key, cat_key.replace("_", " ").title()),
                    rules=buckets[cat_key],
                )
            )

    # Append any categories not in the predefined order
    for cat_key, cat_rules in buckets.items():
        if cat_key not in _CATEGORY_ORDER:
            categories.append(
                LibraryCategory(
                    category=cat_key,
                    display_name=_CATEGORY_DISPLAY.get(cat_key, cat_key.replace("_", " ").title()),
                    rules=cat_rules,
                )
            )

    return categories


@router.get(
    "",
    response_model=LibraryResponse,
    summary="List rule library",
    description="Returns all pre-built detection rule templates grouped by category.",
)
async def list_library(
    current_user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> LibraryResponse:
    """Return all pre-built detection rule templates grouped by category."""
    rules = _load_library()
    categories = _group_by_category(rules)
    return LibraryResponse(
        categories=categories,
        total_rules=len(rules),
    )


@router.post(
    "/{slug}/enable",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enable a library rule",
    description=(
        "Creates an active detection rule from a library template with recommended defaults."
    ),
    dependencies=[Depends(verify_csrf)],
)
async def enable_library_rule(
    slug: str,
    body: EnableRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    db: AsyncSession = Depends(get_db),
    valkey: Any = Depends(get_valkey),
) -> RuleResponse:
    """Create an active rule from a library template."""
    # Find the template
    rules = _load_library()
    template = next((r for r in rules if r["slug"] == slug), None)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library rule '{slug}' not found.",
        )

    # Check if a rule with this slug already exists
    existing = await rule_service.get_rule_by_slug(db, slug)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A rule with slug '{slug}' already exists (id={existing.id}). "
            "Use the customize endpoint to create a variant.",
        )

    overrides = body or EnableRequest()

    payload = RuleCreate(
        name=template["name"],
        slug=template["slug"],
        description=template.get("description"),
        category=template["category"],
        default_severity=overrides.severity or template["default_severity"],
        default_confidence=overrides.confidence or template.get("default_confidence", "medium"),
        logic_type=template["logic_type"],
        logic_config=template["logic_config"],
        enabled=overrides.enabled,
        status="active",
    )

    rule = await rule_service.create_rule(db, payload, created_by=current_user.github_login)
    await db.commit()

    logger.info(
        "rule_library.enabled",
        slug=slug,
        rule_id=rule.id,
        actor=current_user.github_login,
    )
    return RuleResponse.model_validate(rule)


@router.get(
    "/{slug}/customize",
    response_model=CustomizeResponse,
    summary="Get library rule for customization",
    description="Returns a pre-filled rule creation payload that can be modified before enabling.",
)
async def customize_library_rule(
    slug: str,
    current_user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> CustomizeResponse:
    """Return a pre-filled rule create payload for customization."""
    rules = _load_library()
    template = next((r for r in rules if r["slug"] == slug), None)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library rule '{slug}' not found.",
        )

    payload = RuleCreate(
        name=template["name"],
        slug=template["slug"],
        description=template.get("description"),
        category=template["category"],
        default_severity=template["default_severity"],
        default_confidence=template.get("default_confidence", "medium"),
        logic_type=template["logic_type"],
        logic_config=template["logic_config"],
        enabled=False,
        status="draft",
    )

    return CustomizeResponse(rule=payload)
