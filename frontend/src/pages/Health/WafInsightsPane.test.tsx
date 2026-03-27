import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { WafInsightsPane } from './WafInsightsPane';
import { WAF_FINDINGS, PILLAR_META } from './healthData';

describe('WafInsightsPane', () => {
  it('renders the sample data banner', () => {
    render(<WafInsightsPane />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/WAF alignment signals/)).toBeInTheDocument();
  });

  it('renders WAF header info note', () => {
    render(<WafInsightsPane />);
    expect(screen.getByText(/GitHub Well-Architected Framework/)).toBeInTheDocument();
  });

  it('renders WAF Library link', () => {
    render(<WafInsightsPane />);
    const wafLink = screen.getByText('WAF Library ↗');
    expect(wafLink).toBeInTheDocument();
    expect(wafLink.closest('a')).toHaveAttribute(
      'href',
      'https://wellarchitected.github.com/library/scenarios/anti-patterns/',
    );
    expect(wafLink.closest('a')).toHaveAttribute('target', '_blank');
    expect(wafLink.closest('a')).toHaveAttribute('rel', 'noopener');
  });

  it('renders all 5 pillar summary cards', () => {
    render(<WafInsightsPane />);
    // Pillar labels appear multiple times (pillar card + section header + finding tags)
    const govLabels = screen.getAllByText('📜 Governance');
    expect(govLabels.length).toBeGreaterThanOrEqual(1);
    const secLabels = screen.getAllByText('🔒 App Security');
    expect(secLabels.length).toBeGreaterThanOrEqual(1);
    const archLabels = screen.getAllByText('📐 Architecture');
    expect(archLabels.length).toBeGreaterThanOrEqual(1);
    const collabLabels = screen.getAllByText('👥 Collaboration');
    expect(collabLabels.length).toBeGreaterThanOrEqual(1);
    const prodLabels = screen.getAllByText('⚙️ Productivity');
    expect(prodLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows correct finding counts per pillar', () => {
    render(<WafInsightsPane />);
    // Governance: 2 critical + 2 warning = 4
    // App Security: 2 critical + 1 warning = 3
    // Architecture: 1 warning
    // Collaboration: 1 warning
    // Both Architecture and Collaboration have "1 warn"
    const governanceSummary = screen.getByText('2 critical · 2 warn');
    expect(governanceSummary).toBeInTheDocument();

    const appsecSummary = screen.getByText('2 critical · 1 warn');
    expect(appsecSummary).toBeInTheDocument();

    const oneWarnLabels = screen.getAllByText('1 warn');
    expect(oneWarnLabels.length).toBe(2);
    expect(screen.getByText('no issues detected')).toBeInTheDocument();
  });

  it('renders pillar section headers with View pillar links', () => {
    render(<WafInsightsPane />);
    const viewLinks = screen.getAllByText('View pillar ↗');
    expect(viewLinks.length).toBe(5);

    // Each should be an external link
    for (const link of viewLinks) {
      const anchor = link.closest('a');
      expect(anchor).toHaveAttribute('target', '_blank');
      expect(anchor).toHaveAttribute('rel', 'noopener');
    }
  });

  it('renders governance pillar link pointing to correct URL', () => {
    render(<WafInsightsPane />);
    const viewLinks = screen.getAllByText('View pillar ↗');
    const govLink = viewLinks[0].closest('a');
    expect(govLink).toHaveAttribute('href', PILLAR_META.governance.url);
  });

  it('renders evaluated findings with severity dots', () => {
    render(<WafInsightsPane />);
    const evaluatedFindings = WAF_FINDINGS.filter((f) => f.evaluated);
    for (const f of evaluatedFindings) {
      expect(screen.getByText(f.finding)).toBeInTheDocument();
    }
  });

  it('renders critical findings with correct severity dot class', () => {
    render(<WafInsightsPane />);
    const criticalFinding = screen.getByText(
      'Push protection bypasses recorded — 4 events in last 90 days',
    );
    const findingContainer = criticalFinding.closest(`.wafFinding`);
    expect(findingContainer).toBeTruthy();
    expect(findingContainer!.classList.contains('wafFindingCritical')).toBe(true);
  });

  it('renders warning findings with correct styling', () => {
    render(<WafInsightsPane />);
    const warningFinding = screen.getByText(
      'Webhooks without secrets — 3 webhooks configured without a secret token',
    );
    const findingContainer = warningFinding.closest(`.wafFinding`);
    expect(findingContainer).toBeTruthy();
    expect(findingContainer!.classList.contains('wafFindingWarning')).toBe(true);
  });

  it('renders finding detail text', () => {
    render(<WafInsightsPane />);
    expect(
      screen.getByText(/Secret push protection was bypassed 4 times/),
    ).toBeInTheDocument();
  });

  it('renders WAF reference links for each evaluated finding', () => {
    render(<WafInsightsPane />);
    const evaluatedFindings = WAF_FINDINGS.filter((f) => f.evaluated);
    // Some findings share the same WAF ref label, so check unique labels
    const uniqueLabels = new Set(evaluatedFindings.map((f) => `${f.wafRef.label} ↗`));
    for (const label of uniqueLabels) {
      const links = screen.getAllByText(label);
      expect(links.length).toBeGreaterThanOrEqual(1);
      for (const link of links) {
        expect(link.closest('a')).toHaveAttribute('target', '_blank');
      }
    }
  });

  it('renders productivity section with no issues message', () => {
    render(<WafInsightsPane />);
    expect(screen.getByText(/No productivity anti-patterns detected/)).toBeInTheDocument();
  });

  it('renders unevaluated signals section', () => {
    render(<WafInsightsPane />);
    expect(
      screen.getByText('Signals that require active API polling (not evaluated)'),
    ).toBeInTheDocument();
  });

  it('renders unevaluated signals table with correct columns', () => {
    render(<WafInsightsPane />);
    const unevaluatedFindings = WAF_FINDINGS.filter((f) => !f.evaluated);
    // Find the table containing unevaluated signals
    const signalHeader = screen.getByText('Signal');
    const table = signalHeader.closest('table')!;
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.map((h) => h.textContent)).toEqual([
      'Signal',
      'Pillar',
      'Why not available',
      'WAF Reference',
    ]);

    // Check all unevaluated findings are in the table
    for (const f of unevaluatedFindings) {
      expect(within(table).getByText(f.finding)).toBeInTheDocument();
    }
  });

  it('renders all unevaluated findings with evidence text', () => {
    render(<WafInsightsPane />);
    const unevaluatedFindings = WAF_FINDINGS.filter((f) => !f.evaluated);
    for (const f of unevaluatedFindings) {
      expect(screen.getByText(f.evidence)).toBeInTheDocument();
    }
  });

  it('renders baseline import note', () => {
    render(<WafInsightsPane />);
    expect(
      screen.getByText(/perform a one-time baseline import/),
    ).toBeInTheDocument();
  });

  it('renders pillar tags on findings', () => {
    render(<WafInsightsPane />);
    // Governance findings should have the governance tag (multiple times in pillar card + finding + section header)
    const governanceTags = screen.getAllByText('📜 Governance');
    // At minimum: 1 pillar card label + 1 section header + findings
    expect(governanceTags.length).toBeGreaterThanOrEqual(3);
  });

  it('renders evidence sources as code-styled spans', () => {
    render(<WafInsightsPane />);
    // Check a known evidence source is rendered
    const sources = screen.getAllByText('secret_scanning.push_protection.bypass');
    expect(sources.length).toBeGreaterThanOrEqual(1);
    expect(sources[0].classList.contains('wafSource')).toBe(true);
  });

  it('renders correct number of evaluated vs unevaluated findings', () => {
    render(<WafInsightsPane />);
    const evaluated = WAF_FINDINGS.filter((f) => f.evaluated);
    const unevaluated = WAF_FINDINGS.filter((f) => !f.evaluated);

    expect(evaluated.length).toBe(9);
    expect(unevaluated.length).toBe(5);
  });

  it('renders external links with proper security attributes', () => {
    render(<WafInsightsPane />);
    const allLinks = document.querySelectorAll('a[target="_blank"]');
    for (const link of allLinks) {
      expect(link.getAttribute('rel')).toContain('noopener');
    }
  });
});
