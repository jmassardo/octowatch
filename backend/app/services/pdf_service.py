"""PDF/HTML report generation service for compliance reports.

Renders compliance report data into HTML using Jinja2 templates.
The generated HTML includes print-ready CSS suitable for browser-based
PDF export (Ctrl+P / window.print()).

In a production deployment, WeasyPrint or ReportLab can be integrated to
generate true PDF files server-side.
"""

from __future__ import annotations

from typing import Any

import structlog
from jinja2 import Environment, PackageLoader, select_autoescape

logger = structlog.get_logger(__name__)

_jinja_env = Environment(
    loader=PackageLoader("app", "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_compliance_report_html(
    report_data: dict[str, Any],
    *,
    print_ready: bool = False,
) -> str:
    """Render a compliance report dict into an HTML document.

    Args:
        report_data: The structured compliance report from the compliance
            report service (SOC 2, ISO 27001, or NIST CSF).
        print_ready: When True, adds print-optimized CSS for PDF export.

    Returns:
        A complete HTML document string.
    """
    framework = report_data.get("framework", "Compliance Report")
    logger.info("pdf_service.render_html", framework=framework)

    template = _jinja_env.get_template("compliance_report.html")
    return template.render(
        report=report_data,
        print_ready=print_ready,
    )
