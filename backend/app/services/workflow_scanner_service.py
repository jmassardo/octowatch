"""GitHub Actions workflow security scanner.

Parses workflow YAML files and checks for insecure patterns such as:
- Unpinned action versions (tags/branches instead of SHAs)
- ``pull_request_target`` with ``actions/checkout`` (code injection vector)
- Secrets exposed to pull-request context
- Overly permissive ``permissions`` (``write-all``)
- Self-hosted runner usage (requires security review)
- Script injection via untrusted input in ``run:`` blocks
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class WorkflowScanFinding:
    """A single security finding from workflow analysis."""

    rule_id: str
    severity: str
    title: str
    description: str
    workflow_path: str
    details: dict[str, Any] = field(default_factory=dict)
    suggested_fix: str | None = None


@dataclass
class WorkflowScanResult:
    """Scan result for a single workflow file."""

    workflow_path: str
    findings: list[WorkflowScanFinding] = field(default_factory=list)
    score: int = 100  # 0-100, deducted per finding


# Severity weights for score calculation
_SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 25,
    "high": 15,
    "medium": 10,
    "low": 5,
}

# SHA pattern: 40 hex chars (full SHA-1) or 64 hex chars (SHA-256)
_SHA_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$", re.IGNORECASE)

# Contexts that may contain untrusted user input
_DANGEROUS_CONTEXTS = [
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.comment.body",
    "github.event.review.body",
    "github.event.head_commit.message",
    "github.head_ref",
    "github.event.pull_request.head.ref",
    "github.event.pull_request.head.label",
]


class WorkflowScannerService:
    """Scan GitHub Actions workflow YAML files for security issues."""

    def scan_workflow(
        self,
        yaml_content: str,
        workflow_path: str,
        repo: str = "",
    ) -> WorkflowScanResult:
        """Parse and analyse a workflow YAML file.

        Parameters
        ----------
        yaml_content:
            Raw YAML content of the workflow file.
        workflow_path:
            Path within the repository (e.g. ``.github/workflows/ci.yml``).
        repo:
            Repository slug (``org/name``).

        Returns
        -------
        WorkflowScanResult
            Findings and an overall security score.
        """
        result = WorkflowScanResult(workflow_path=workflow_path)

        try:
            workflow = yaml.safe_load(yaml_content)
        except yaml.YAMLError as exc:
            result.findings.append(
                WorkflowScanFinding(
                    rule_id="malformed-yaml",
                    severity="medium",
                    title="Malformed workflow YAML",
                    description=f"Could not parse workflow file: {exc}",
                    workflow_path=workflow_path,
                )
            )
            result.score = 50
            return result

        if not isinstance(workflow, dict):
            return result

        # YAML resolves the bare key `on` as boolean True; also check `True`
        triggers_raw = workflow.get("on") or workflow.get(True, {})
        triggers = _normalise_triggers(triggers_raw)
        top_permissions = workflow.get("permissions", None)
        jobs: dict[str, Any] = workflow.get("jobs", {}) or {}

        self._check_permissions(top_permissions, workflow_path, result, scope="workflow")

        for job_name, job_def in jobs.items():
            if not isinstance(job_def, dict):
                continue

            # Check job-level permissions
            job_perms = job_def.get("permissions", None)
            self._check_permissions(job_perms, workflow_path, result, scope=f"job '{job_name}'")

            # Self-hosted runner
            runs_on = job_def.get("runs-on", "")
            self._check_self_hosted(runs_on, workflow_path, job_name, result)

            steps = job_def.get("steps", []) or []
            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                uses = step.get("uses")
                if uses:
                    self._check_action_pinning(uses, workflow_path, job_name, step_idx, result)
                    self._check_pr_target_checkout(
                        uses, triggers, workflow_path, job_name, step_idx, result
                    )

                run_cmd = step.get("run")
                if run_cmd:
                    self._check_script_injection(run_cmd, workflow_path, job_name, step_idx, result)

            # Check secret exposure in PR context
            self._check_secrets_in_pr(job_def, triggers, workflow_path, job_name, result)

        # Compute score
        total_deduction = sum(_SEVERITY_WEIGHTS.get(f.severity, 5) for f in result.findings)
        result.score = max(0, 100 - total_deduction)

        return result

    def suggest_fix(self, finding: WorkflowScanFinding) -> str:
        """Return a remediated YAML snippet for a finding."""
        if finding.suggested_fix:
            return finding.suggested_fix
        return f"# No automatic fix available for rule: {finding.rule_id}"

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_action_pinning(
        self,
        uses: str,
        workflow_path: str,
        job_name: str,
        step_idx: int,
        result: WorkflowScanResult,
    ) -> None:
        """Check if a ``uses:`` reference is pinned to a SHA."""
        if uses.startswith("./") or uses.startswith("docker://"):
            return  # local action or Docker — fine

        if "@" not in uses:
            return  # composite action without version — different issue

        _action_ref, version = uses.rsplit("@", 1)
        if _SHA_RE.match(version):
            return  # pinned to SHA ✓

        result.findings.append(
            WorkflowScanFinding(
                rule_id="unpinned-action",
                severity="medium",
                title="Action not pinned to SHA",
                description=(
                    f"Job '{job_name}' step {step_idx} uses '{uses}' which is "
                    f"pinned to a mutable ref (tag/branch). Pin to a full commit "
                    f"SHA to prevent supply-chain attacks."
                ),
                workflow_path=workflow_path,
                details={"uses": uses, "job": job_name, "step_index": step_idx},
                suggested_fix=(
                    f"# Pin to a specific commit SHA:\n"
                    f"# uses: {_action_ref}@<full-commit-sha>  "
                    f"# {version}\n"
                    f"uses: {uses}  # ⚠️ Replace with SHA"
                ),
            )
        )

    def _check_pr_target_checkout(
        self,
        uses: str,
        triggers: set[str],
        workflow_path: str,
        job_name: str,
        step_idx: int,
        result: WorkflowScanResult,
    ) -> None:
        """Detect pull_request_target with checkout — code injection risk."""
        if "pull_request_target" not in triggers:
            return
        if "actions/checkout" not in uses:
            return

        result.findings.append(
            WorkflowScanFinding(
                rule_id="pull-request-target-checkout",
                severity="critical",
                title="pull_request_target with checkout",
                description=(
                    f"Job '{job_name}' step {step_idx} checks out code in a "
                    f"pull_request_target workflow. This allows PRs from forks "
                    f"to execute arbitrary code with write permissions and access "
                    f"to secrets."
                ),
                workflow_path=workflow_path,
                details={"uses": uses, "job": job_name, "step_index": step_idx},
                suggested_fix=(
                    "# Option 1: Use pull_request instead of pull_request_target\n"
                    "on:\n"
                    "  pull_request:\n"
                    "    branches: [main]\n\n"
                    "# Option 2: If you must use pull_request_target,\n"
                    "# do NOT checkout PR code. Only checkout base branch."
                ),
            )
        )

    def _check_permissions(
        self,
        permissions: Any,
        workflow_path: str,
        result: WorkflowScanResult,
        scope: str = "workflow",
    ) -> None:
        """Check for overly permissive permissions."""
        if permissions is None:
            return

        if isinstance(permissions, str) and permissions.strip() == "write-all":
            result.findings.append(
                WorkflowScanFinding(
                    rule_id="excessive-permissions",
                    severity="high",
                    title="Excessive write-all permissions",
                    description=(
                        f"The {scope} uses 'write-all' permissions, granting "
                        f"broad write access. Apply the principle of least privilege."
                    ),
                    workflow_path=workflow_path,
                    details={"permissions": permissions, "scope": scope},
                    suggested_fix=(
                        "permissions:\n"
                        "  contents: read\n"
                        "  # Add only the specific permissions needed"
                    ),
                )
            )

    def _check_self_hosted(
        self,
        runs_on: Any,
        workflow_path: str,
        job_name: str,
        result: WorkflowScanResult,
    ) -> None:
        """Flag self-hosted runner usage for security review."""
        label = str(runs_on) if not isinstance(runs_on, list) else " ".join(str(r) for r in runs_on)
        if "self-hosted" in label.lower():
            result.findings.append(
                WorkflowScanFinding(
                    rule_id="self-hosted-runner",
                    severity="low",
                    title="Self-hosted runner usage",
                    description=(
                        f"Job '{job_name}' runs on a self-hosted runner. "
                        f"Ensure runner security hardening is applied."
                    ),
                    workflow_path=workflow_path,
                    details={"runs_on": runs_on, "job": job_name},
                )
            )

    def _check_script_injection(
        self,
        run_cmd: str,
        workflow_path: str,
        job_name: str,
        step_idx: int,
        result: WorkflowScanResult,
    ) -> None:
        """Detect untrusted user input in run: blocks (script injection)."""
        for ctx in _DANGEROUS_CONTEXTS:
            pattern = "${{ " + ctx + " }}"
            if pattern in run_cmd or f"${{{ctx}}}" in run_cmd.replace(" ", ""):
                result.findings.append(
                    WorkflowScanFinding(
                        rule_id="script-injection",
                        severity="critical",
                        title="Script injection via untrusted input",
                        description=(
                            f"Job '{job_name}' step {step_idx} uses '{ctx}' "
                            f"directly in a 'run:' block. An attacker can craft "
                            f"a malicious value to execute arbitrary commands."
                        ),
                        workflow_path=workflow_path,
                        details={
                            "context": ctx,
                            "job": job_name,
                            "step_index": step_idx,
                        },
                        suggested_fix=(
                            "# Use an environment variable instead:\n"
                            "env:\n"
                            f"  UNTRUSTED_INPUT: ${{{{ {ctx} }}}}\n"
                            "run: |\n"
                            '  echo "$UNTRUSTED_INPUT"'
                        ),
                    )
                )
                break  # One finding per step is enough

    def _check_secrets_in_pr(
        self,
        job_def: dict[str, Any],
        triggers: set[str],
        workflow_path: str,
        job_name: str,
        result: WorkflowScanResult,
    ) -> None:
        """Detect secrets accessible in pull_request context."""
        if "pull_request_target" not in triggers:
            return

        job_str = yaml.dump(job_def, default_flow_style=False)
        if "secrets." in job_str:
            result.findings.append(
                WorkflowScanFinding(
                    rule_id="secret-in-pr",
                    severity="high",
                    title="Secrets exposed in pull_request_target context",
                    description=(
                        f"Job '{job_name}' references secrets in a "
                        f"pull_request_target workflow. Secrets may be "
                        f"accessible to code from untrusted forks."
                    ),
                    workflow_path=workflow_path,
                    details={"job": job_name},
                    suggested_fix=(
                        "# Move secret-using steps to a separate workflow\n"
                        "# triggered by workflow_run, which only runs after\n"
                        "# the PR workflow completes on the base branch."
                    ),
                )
            )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _normalise_triggers(on_value: Any) -> set[str]:
    """Extract trigger event names from the ``on:`` key."""
    if isinstance(on_value, str):
        return {on_value}
    if isinstance(on_value, list):
        return {str(t) for t in on_value}
    if isinstance(on_value, dict):
        return set(on_value.keys())
    return set()
