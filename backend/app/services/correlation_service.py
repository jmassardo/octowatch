"""Correlation engine: groups related detections into investigation chains."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.correlation import ChainMembership, CorrelationChain
from app.models.detection import Detection, RuleDefinition

logger = structlog.get_logger(__name__)

# ── Correlation time windows (seconds) ────────────────────────────────────────

WINDOW_ACTOR_TARGET_HOURS = 24
WINDOW_ACTOR_CATEGORY_HOURS = 1
WINDOW_TARGET_SEVERITY_HOURS = 6

# ── Severity ordering for chain roll-up ───────────────────────────────────────

SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}


def _highest_severity(a: str, b: str) -> str:
    """Return the higher of two severity strings."""
    return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class CorrelationMatch:
    """A single match found by a correlation strategy."""

    detection_id: int
    correlation_type: str
    confidence: float


@dataclass
class CorrelationResult:
    """Result of running correlation for a single detection."""

    detection_id: int
    chain_id: str | None = None
    matches: list[CorrelationMatch] = field(default_factory=list)
    created_new_chain: bool = False


@dataclass
class InvestigationChain:
    """Fully-hydrated investigation chain with member detections."""

    chain_id: str
    title: str
    status: str
    severity: str
    assignee: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    members: list[ChainMemberInfo] = field(default_factory=list)


@dataclass
class ChainMemberInfo:
    """Detection membership info within a chain."""

    detection_id: int
    correlation_type: str
    confidence: float
    added_at: datetime
    detection_title: str
    detection_severity: str
    detection_status: str
    detection_actor: str | None
    detection_triggered_at: datetime


# ── Correlation engine ────────────────────────────────────────────────────────


class CorrelationEngine:
    """Correlates related detections into investigation chains."""

    async def correlate_detection(
        self, detection_id: int, session: AsyncSession
    ) -> CorrelationResult:
        """Find and link related detections for a given detection.

        Correlation strategies (in priority order):
        1. Same actor + same target within 24h window
        2. Same actor + same rule category within 1h
        3. Same target (repo/org) + same severity within 6h
        4. Chain rule matches (detections already in chains with matching patterns)
        """
        result = CorrelationResult(detection_id=detection_id)

        # Load the detection with its rule
        stmt = (
            select(Detection)
            .where(Detection.id == detection_id)
            .execution_options(populate_existing=True)
        )
        row = await session.execute(stmt)
        detection = row.scalar_one_or_none()
        if detection is None:
            logger.warning("correlation.detection_not_found", detection_id=detection_id)
            return result

        # Load the rule for category info
        rule: RuleDefinition | None = None
        if detection.rule_id:
            rule_stmt = select(RuleDefinition).where(RuleDefinition.id == detection.rule_id)
            rule_row = await session.execute(rule_stmt)
            rule = rule_row.scalar_one_or_none()

        # If detection already belongs to a chain, return early
        if detection.chain_id:
            result.chain_id = detection.chain_id
            return result

        matches: list[CorrelationMatch] = []

        # Strategy 1: Same actor + same target (repo or org) within 24h
        if detection.actor and (detection.repo or detection.org):
            matches.extend(await self._find_actor_target_matches(detection, session))

        # Strategy 2: Same actor + same rule category within 1h
        if detection.actor and rule:
            matches.extend(
                await self._find_actor_category_matches(detection, rule.category, session)
            )

        # Strategy 3: Same target + same severity within 6h
        if detection.repo or detection.org:
            matches.extend(await self._find_target_severity_matches(detection, session))

        # Strategy 4: Chain rule matches (existing chains with matching detections)
        matches.extend(await self._find_chain_rule_matches(detection, session))

        # De-duplicate matches by detection_id, keeping highest confidence
        seen: dict[int, CorrelationMatch] = {}
        for m in matches:
            if m.detection_id == detection_id:
                continue
            if m.detection_id not in seen or m.confidence > seen[m.detection_id].confidence:
                seen[m.detection_id] = m

        result.matches = list(seen.values())

        if not result.matches:
            return result

        # Check if any matched detections already belong to a chain
        matched_ids = [m.detection_id for m in result.matches]
        existing_chain_stmt = (
            select(Detection.chain_id)
            .where(Detection.id.in_(matched_ids))
            .where(Detection.chain_id.isnot(None))
            .limit(1)
        )
        existing_row = await session.execute(existing_chain_stmt)
        existing_chain_id = existing_row.scalar_one_or_none()

        if existing_chain_id:
            # Add detection to existing chain
            chain_id = existing_chain_id
            result.chain_id = chain_id
            result.created_new_chain = False
        else:
            # Create a new chain
            chain_id = str(uuid.uuid4())
            best_match = max(result.matches, key=lambda m: m.confidence)
            chain_severity = _highest_severity(
                detection.severity,
                (await self._get_detection_severity(best_match.detection_id, session))
                or detection.severity,
            )
            chain = CorrelationChain(
                id=chain_id,
                title=f"Correlated: {detection.title}",
                status="open",
                severity=chain_severity,
            )
            session.add(chain)
            result.chain_id = chain_id
            result.created_new_chain = True

            # Add matched detections to chain
            for match in result.matches:
                membership = ChainMembership(
                    chain_id=chain_id,
                    detection_id=match.detection_id,
                    correlation_type=match.correlation_type,
                    confidence=match.confidence,
                )
                session.add(membership)
                # Update the matched detection's chain_id
                matched_det_stmt = select(Detection).where(Detection.id == match.detection_id)
                matched_det_row = await session.execute(matched_det_stmt)
                matched_det = matched_det_row.scalar_one_or_none()
                if matched_det:
                    matched_det.chain_id = chain_id

        # Add the source detection to the chain
        source_membership = ChainMembership(
            chain_id=chain_id,
            detection_id=detection_id,
            correlation_type="source",
            confidence=1.0,
        )
        session.add(source_membership)
        detection.chain_id = chain_id

        # Update chain severity to highest member severity
        await self._update_chain_severity(chain_id, session)

        await session.flush()

        logger.info(
            "correlation.completed",
            detection_id=detection_id,
            chain_id=chain_id,
            match_count=len(result.matches),
            created_new=result.created_new_chain,
        )

        return result

    async def get_investigation_chain(
        self, chain_id: str, session: AsyncSession
    ) -> InvestigationChain | None:
        """Get all detections in a correlation chain."""
        stmt = select(CorrelationChain).where(CorrelationChain.id == chain_id)
        row = await session.execute(stmt)
        chain = row.scalar_one_or_none()
        if chain is None:
            return None

        # Fetch memberships with detection details
        membership_stmt = (
            select(ChainMembership, Detection)
            .join(Detection, ChainMembership.detection_id == Detection.id)
            .where(ChainMembership.chain_id == chain_id)
            .order_by(Detection.triggered_at.asc())
        )
        membership_rows = await session.execute(membership_stmt)

        members: list[ChainMemberInfo] = []
        for membership, det in membership_rows:
            members.append(
                ChainMemberInfo(
                    detection_id=det.id,
                    correlation_type=membership.correlation_type,
                    confidence=membership.confidence,
                    added_at=membership.added_at,
                    detection_title=det.title,
                    detection_severity=det.severity,
                    detection_status=det.status,
                    detection_actor=det.actor,
                    detection_triggered_at=det.triggered_at,
                )
            )

        return InvestigationChain(
            chain_id=chain.id,
            title=chain.title,
            status=chain.status,
            severity=chain.severity,
            assignee=chain.assignee,
            notes=chain.notes,
            created_at=chain.created_at,
            updated_at=chain.updated_at,
            resolved_at=chain.resolved_at,
            members=members,
        )

    async def merge_chains(self, chain_ids: list[str], session: AsyncSession) -> str | None:
        """Merge multiple chains into one investigation.

        Returns the surviving chain ID, or None if no valid chains found.
        """
        if len(chain_ids) < 2:
            return chain_ids[0] if chain_ids else None

        # Load all chains
        stmt = select(CorrelationChain).where(CorrelationChain.id.in_(chain_ids))
        rows = await session.execute(stmt)
        chains = list(rows.scalars().all())

        if len(chains) < 2:
            return chains[0].id if chains else None

        # The primary chain is the one created first
        chains.sort(key=lambda c: c.created_at)
        primary = chains[0]
        secondary_ids = [c.id for c in chains[1:]]

        # Merge severity — use highest
        merged_severity = primary.severity
        for chain in chains[1:]:
            merged_severity = _highest_severity(merged_severity, chain.severity)
        primary.severity = merged_severity

        # Re-assign memberships from secondary chains to primary
        for secondary_id in secondary_ids:
            update_memberships_stmt = select(ChainMembership).where(
                ChainMembership.chain_id == secondary_id
            )
            membership_rows = await session.execute(update_memberships_stmt)
            for membership in membership_rows.scalars().all():
                # Check if detection already in primary chain
                existing_stmt = (
                    select(ChainMembership)
                    .where(ChainMembership.chain_id == primary.id)
                    .where(ChainMembership.detection_id == membership.detection_id)
                )
                existing = (await session.execute(existing_stmt)).scalar_one_or_none()
                if existing is None:
                    new_membership = ChainMembership(
                        chain_id=primary.id,
                        detection_id=membership.detection_id,
                        correlation_type=membership.correlation_type,
                        confidence=membership.confidence,
                    )
                    session.add(new_membership)

            # Update detections to point to primary chain
            det_stmt = select(Detection).where(Detection.chain_id == secondary_id)
            det_rows = await session.execute(det_stmt)
            for det in det_rows.scalars().all():
                det.chain_id = primary.id

            # Delete secondary chain (cascades memberships)
            secondary_stmt = select(CorrelationChain).where(CorrelationChain.id == secondary_id)
            secondary_row = await session.execute(secondary_stmt)
            secondary_chain = secondary_row.scalar_one_or_none()
            if secondary_chain:
                await session.delete(secondary_chain)

        await session.flush()

        logger.info(
            "correlation.chains_merged",
            primary_chain_id=primary.id,
            merged_chain_ids=secondary_ids,
        )

        return primary.id

    # ── Private correlation strategies ────────────────────────────────────────

    async def _find_actor_target_matches(
        self, detection: Detection, session: AsyncSession
    ) -> list[CorrelationMatch]:
        """Strategy 1: Same actor + same target within 24h."""
        cutoff = detection.triggered_at - timedelta(hours=WINDOW_ACTOR_TARGET_HOURS)
        stmt = (
            select(Detection)
            .where(Detection.id != detection.id)
            .where(Detection.actor == detection.actor)
            .where(Detection.triggered_at >= cutoff)
            .where(Detection.triggered_at <= detection.triggered_at)
        )
        if detection.repo:
            stmt = stmt.where(Detection.repo == detection.repo)
        elif detection.org:
            stmt = stmt.where(Detection.org == detection.org)
        else:
            return []

        rows = await session.execute(stmt)
        return [
            CorrelationMatch(
                detection_id=d.id,
                correlation_type="actor_target",
                confidence=0.9,
            )
            for d in rows.scalars().all()
        ]

    async def _find_actor_category_matches(
        self, detection: Detection, category: str, session: AsyncSession
    ) -> list[CorrelationMatch]:
        """Strategy 2: Same actor + same rule category within 1h."""
        cutoff = detection.triggered_at - timedelta(hours=WINDOW_ACTOR_CATEGORY_HOURS)
        stmt = (
            select(Detection)
            .join(RuleDefinition, Detection.rule_id == RuleDefinition.id)
            .where(Detection.id != detection.id)
            .where(Detection.actor == detection.actor)
            .where(RuleDefinition.category == category)
            .where(Detection.triggered_at >= cutoff)
            .where(Detection.triggered_at <= detection.triggered_at)
        )
        rows = await session.execute(stmt)
        return [
            CorrelationMatch(
                detection_id=d.id,
                correlation_type="actor_category",
                confidence=0.8,
            )
            for d in rows.scalars().all()
        ]

    async def _find_target_severity_matches(
        self, detection: Detection, session: AsyncSession
    ) -> list[CorrelationMatch]:
        """Strategy 3: Same target + same severity within 6h."""
        cutoff = detection.triggered_at - timedelta(hours=WINDOW_TARGET_SEVERITY_HOURS)
        stmt = (
            select(Detection)
            .where(Detection.id != detection.id)
            .where(Detection.severity == detection.severity)
            .where(Detection.triggered_at >= cutoff)
            .where(Detection.triggered_at <= detection.triggered_at)
        )
        if detection.repo:
            stmt = stmt.where(Detection.repo == detection.repo)
        elif detection.org:
            stmt = stmt.where(Detection.org == detection.org)
        else:
            return []

        rows = await session.execute(stmt)
        return [
            CorrelationMatch(
                detection_id=d.id,
                correlation_type="target_severity",
                confidence=0.7,
            )
            for d in rows.scalars().all()
        ]

    async def _find_chain_rule_matches(
        self, detection: Detection, session: AsyncSession
    ) -> list[CorrelationMatch]:
        """Strategy 4: Detections already in chains that share actor or target."""
        if not detection.actor and not detection.repo and not detection.org:
            return []

        # Find detections already in chains that share our actor or target
        stmt = select(Detection).where(
            Detection.id != detection.id,
            Detection.chain_id.isnot(None),
        )
        conditions = []
        if detection.actor:
            conditions.append(Detection.actor == detection.actor)
        if detection.repo:
            conditions.append(Detection.repo == detection.repo)
        elif detection.org:
            conditions.append(Detection.org == detection.org)

        if not conditions:
            return []

        from sqlalchemy import or_

        stmt = stmt.where(or_(*conditions))
        rows = await session.execute(stmt)

        return [
            CorrelationMatch(
                detection_id=d.id,
                correlation_type="chain_rule",
                confidence=0.6,
            )
            for d in rows.scalars().all()
        ]

    async def _get_detection_severity(self, detection_id: int, session: AsyncSession) -> str | None:
        """Fetch the severity of a detection by ID."""
        stmt = select(Detection.severity).where(Detection.id == detection_id)
        row = await session.execute(stmt)
        return row.scalar_one_or_none()

    async def _update_chain_severity(self, chain_id: str, session: AsyncSession) -> None:
        """Update a chain's severity to the highest among its members."""
        stmt = select(Detection.severity).where(Detection.chain_id == chain_id)
        rows = await session.execute(stmt)
        severities = list(rows.scalars().all())
        if not severities:
            return

        highest = severities[0]
        for s in severities[1:]:
            highest = _highest_severity(highest, s)

        chain_stmt = select(CorrelationChain).where(CorrelationChain.id == chain_id)
        chain_row = await session.execute(chain_stmt)
        chain = chain_row.scalar_one_or_none()
        if chain:
            chain.severity = highest
