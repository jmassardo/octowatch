import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WafInsightsPane } from './WafInsightsPane';
import { PILLAR_META } from './healthData';

vi.mock('../../api/healthSignals', () => ({
  getWafFindings: vi.fn(),
}));

const mockFindings = {
  findings: [
    {
      id: 'waf-1',
      pillar: 'governance',
      finding: 'PATs without expiry detected',
      severity: 'critical',
      status: 'open',
      evaluated: true,
      detail: 'Several PATs have no expiry set.',
      evidence_count: 12,
      evidence: [{ actor: 'user1', count: 5 }],
    },
    {
      id: 'waf-2',
      pillar: 'governance',
      finding: 'Org members without 2FA',
      severity: 'warning',
      status: 'open',
      evaluated: true,
      detail: 'Some members have not enabled 2FA.',
      evidence_count: 3,
    },
    {
      id: 'waf-3',
      pillar: 'appsec',
      finding: 'Push protection bypasses recorded',
      severity: 'critical',
      status: 'open',
      evaluated: true,
      detail: 'Secret push protection was bypassed multiple times.',
      evidence_count: 4,
    },
    {
      id: 'waf-4',
      pillar: 'architecture',
      finding: 'Monorepo with excessive team count',
      severity: 'warning',
      status: 'open',
      evaluated: true,
      detail: 'Too many teams assigned to a single repo.',
      evidence_count: 7,
    },
    {
      id: 'waf-5',
      pillar: 'collaboration',
      finding: 'PRs merged without review',
      severity: 'warning',
      status: 'open',
      evaluated: true,
      detail: 'Multiple PRs were merged without any review.',
      evidence_count: 15,
    },
  ],
};

let mockQueryReturn: {
  data: typeof mockFindings | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => mockQueryReturn,
  };
});

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <WafInsightsPane />
    </QueryClientProvider>,
  );
}

describe('WafInsightsPane', () => {
  beforeEach(() => {
    mockQueryReturn = {
      data: mockFindings,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  });

  it('shows loading spinner when loading', () => {
    mockQueryReturn = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('shows error banner on error', () => {
    mockQueryReturn = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPane();
    expect(screen.getByText('Failed to load WAF findings')).toBeInTheDocument();
  });

  it('renders WAF header info note', () => {
    renderPane();
    expect(screen.getByText(/GitHub Well-Architected Framework/)).toBeInTheDocument();
  });

  it('renders WAF Library link', () => {
    renderPane();
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
    renderPane();
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

  it('renders evaluated finding titles', () => {
    renderPane();
    expect(screen.getByText('PATs without expiry detected')).toBeInTheDocument();
    expect(screen.getByText('Push protection bypasses recorded')).toBeInTheDocument();
    expect(screen.getByText('PRs merged without review')).toBeInTheDocument();
  });

  it('hides finding detail text when collapsed', () => {
    renderPane();
    // Details should be hidden in collapsed state (via CSS class)
    const finding = screen.getByText('PATs without expiry detected').closest('[role="button"]');
    expect(finding).toHaveClass(/findingCollapsed/);
  });

  it('expands finding to show detail text when clicked', async () => {
    const user = userEvent.setup();
    renderPane();
    const finding = screen.getByText('PATs without expiry detected').closest('[role="button"]');
    expect(finding).toBeTruthy();
    await user.click(finding!);
    expect(finding).toHaveClass(/findingExpanded/);
    expect(screen.getByText(/Several PATs have no expiry set/)).toBeInTheDocument();
  });

  it('shows evidence table when finding with evidence is expanded', async () => {
    const user = userEvent.setup();
    renderPane();
    const finding = screen.getByText('PATs without expiry detected').closest('[role="button"]');
    await user.click(finding!);
    expect(screen.getByText('actor')).toBeInTheDocument();
    expect(screen.getByText('user1')).toBeInTheDocument();
  });

  it('shows evidence count when finding is expanded', async () => {
    const user = userEvent.setup();
    renderPane();
    const finding = screen.getByText('PATs without expiry detected').closest('[role="button"]');
    await user.click(finding!);
    expect(screen.getByText('12 events evaluated')).toBeInTheDocument();
  });

  it('collapses finding when clicked again', async () => {
    const user = userEvent.setup();
    renderPane();
    const finding = screen.getByText('PATs without expiry detected').closest('[role="button"]');
    await user.click(finding!);
    expect(finding).toHaveClass(/findingExpanded/);
    await user.click(finding!);
    expect(finding).toHaveClass(/findingCollapsed/);
  });

  it('renders pillar section headers with View pillar links', () => {
    renderPane();
    const viewLinks = screen.getAllByText('View pillar ↗');
    expect(viewLinks.length).toBeGreaterThanOrEqual(1);
    for (const link of viewLinks) {
      const anchor = link.closest('a');
      expect(anchor).toHaveAttribute('target', '_blank');
      expect(anchor).toHaveAttribute('rel', 'noopener');
    }
  });

  it('renders governance pillar link pointing to correct URL', () => {
    renderPane();
    const viewLinks = screen.getAllByText('View pillar ↗');
    const govLink = viewLinks[0].closest('a');
    expect(govLink).toHaveAttribute('href', PILLAR_META.governance.url);
  });

  it('shows empty state when no findings', () => {
    mockQueryReturn = {
      data: { findings: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText(/No WAF findings available/)).toBeInTheDocument();
  });

  it('renders productivity section with no issues message when no productivity findings', () => {
    renderPane();
    expect(screen.getByText(/No productivity anti-patterns detected/)).toBeInTheDocument();
  });

  it('shows sample data banner when findings are empty', () => {
    mockQueryReturn = {
      data: { findings: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText(/This data is illustrative/)).toBeInTheDocument();
  });

  it('does not show sample data banner when real findings exist', () => {
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner during loading state', () => {
    mockQueryReturn = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner during error state', () => {
    mockQueryReturn = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });

  it('renders catalog at bottom of page', () => {
    renderPane();
    expect(screen.getByText('What we check')).toBeInTheDocument();
  });

  it('adds id attributes to pillar sections for scrolling', () => {
    renderPane();
    expect(document.getElementById('pillar-governance')).toBeTruthy();
    expect(document.getElementById('pillar-appsec')).toBeTruthy();
    expect(document.getElementById('pillar-architecture')).toBeTruthy();
    expect(document.getElementById('pillar-collaboration')).toBeTruthy();
    expect(document.getElementById('pillar-productivity')).toBeTruthy();
  });
});
