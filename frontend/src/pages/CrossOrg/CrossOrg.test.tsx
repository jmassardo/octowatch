import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { CrossOrgPage } from './index';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockGetTimeline = vi.fn();
const mockGetCorrelations = vi.fn();

vi.mock('../../api/crossOrg', () => ({
  getCrossOrgTimeline: (...args: unknown[]) => mockGetTimeline(...args),
  getCrossOrgCorrelations: (...args: unknown[]) => mockGetCorrelations(...args),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const CORRELATIONS_RESPONSE = {
  correlations: [
    {
      actor: 'jdoe',
      orgs: ['org-alpha', 'org-beta'],
      org_count: 2,
      event_count: 42,
      distinct_actions: 8,
      first_seen: '2024-06-01T10:00:00Z',
      last_seen: '2024-06-07T15:00:00Z',
      risk_score: 75,
      top_actions: ['org.add_member', 'repo.create'],
    },
    {
      actor: 'asmith',
      orgs: ['org-alpha', 'org-gamma'],
      org_count: 2,
      event_count: 15,
      distinct_actions: 3,
      first_seen: '2024-06-02T08:00:00Z',
      last_seen: '2024-06-06T12:00:00Z',
      risk_score: 30,
    },
  ],
  total: 2,
};

const TIMELINE_RESPONSE = {
  events: [
    {
      id: 1,
      created_at: '2024-06-07T15:00:00Z',
      action: 'org.add_member',
      actor: 'jdoe',
      org: 'org-alpha',
      repo: null,
      source_ip: '1.2.3.4',
      country: 'US',
    },
    {
      id: 2,
      created_at: '2024-06-07T14:30:00Z',
      action: 'repo.create',
      actor: 'jdoe',
      org: 'org-beta',
      repo: 'org-beta/new-repo',
      source_ip: '1.2.3.4',
      country: 'US',
    },
  ],
  total: 2,
};

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('CrossOrgPage — Correlations Tab', () => {
  beforeEach(() => {
    mockGetCorrelations.mockClear();
    mockGetTimeline.mockClear();
    mockGetCorrelations.mockResolvedValue(CORRELATIONS_RESPONSE);
    mockGetTimeline.mockResolvedValue(TIMELINE_RESPONSE);
  });

  it('renders page title', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('Cross-Organization Correlation')).toBeInTheDocument();
  });

  it('renders actor names in the data table', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('jdoe')).toBeInTheDocument();
    expect(await screen.findByText('asmith')).toBeInTheDocument();
  });

  it('shows risk badge with tier and score', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('High (75)')).toBeInTheDocument();
    expect(await screen.findByText('Low (30)')).toBeInTheDocument();
  });

  it('shows org tags (max 3 with +N more for overflow)', async () => {
    renderWithProviders(<CrossOrgPage />);
    const orgAlphaTags = await screen.findAllByText('org-alpha');
    expect(orgAlphaTags.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('org-beta')).toBeInTheDocument();
  });

  it('shows event count in table cell', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('42')).toBeInTheDocument();
  });

  it('shows total actors count in tab badge', async () => {
    renderWithProviders(<CrossOrgPage />);
    // Tab badge shows the total count — find it within the tab button
    const correlationsTab = await screen.findByRole('button', { name: /correlations/i });
    expect(within(correlationsTab).getByText('2')).toBeInTheDocument();
  });

  it('renders improved empty state when no correlations', async () => {
    mockGetCorrelations.mockResolvedValue({ correlations: [], total: 0 });
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('All clear')).toBeInTheDocument();
    expect(
      await screen.findByText(/no suspicious cross-org activity detected/i),
    ).toBeInTheDocument();
  });

  it('shows risk summary MetricCards', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('Total Cross-Org Actors')).toBeInTheDocument();
    expect(await screen.findByText('Critical')).toBeInTheDocument();
    expect(await screen.findByText('High')).toBeInTheDocument();
    expect(await screen.findByText('Medium')).toBeInTheDocument();
    // "Low" appears both as MetricCard label and Label variant
    const lowLabels = await screen.findAllByText('Low');
    expect(lowLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('filters by risk tier when MetricCard is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    // Wait for data to load
    await screen.findByText('jdoe');
    // Click the "High" MetricCard — should filter to only jdoe (score 75)
    const highCard = screen.getByRole('button', { name: 'High' });
    await user.click(highCard);
    // Filter indicator appears
    expect(await screen.findByText('Clear filter')).toBeInTheDocument();
    // asmith (low risk) should not be visible
    expect(screen.queryByText('asmith')).not.toBeInTheDocument();
    // jdoe should still be visible
    expect(screen.getByText('jdoe')).toBeInTheDocument();
  });

  it('clears risk tier filter when clear button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    await screen.findByText('jdoe');
    const highCard = screen.getByRole('button', { name: 'High' });
    await user.click(highCard);
    expect(screen.queryByText('asmith')).not.toBeInTheDocument();
    // Click clear filter
    await user.click(screen.getByText('Clear filter'));
    // asmith should be visible again
    expect(await screen.findByText('asmith')).toBeInTheDocument();
  });

  it('shows Investigate button as quick action', async () => {
    renderWithProviders(<CrossOrgPage />);
    const buttons = await screen.findAllByText('Investigate');
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it('renders collapsible guidance box', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(
      await screen.findByText('What is cross-org monitoring?'),
    ).toBeInTheDocument();
  });

  it('toggles guidance box content on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    const toggle = await screen.findByText('What is cross-org monitoring?');
    // Default collapsed — guidance list should not be visible
    expect(screen.queryByText(/Review high-risk actors/)).not.toBeInTheDocument();
    // Click to expand
    await user.click(toggle);
    expect(await screen.findByText(/Review high-risk actors/)).toBeInTheDocument();
    // Click to collapse again
    await user.click(toggle);
    expect(screen.queryByText(/Review high-risk actors/)).not.toBeInTheDocument();
  });
});

describe('CrossOrgPage — Timeline Tab', () => {
  beforeEach(() => {
    mockGetCorrelations.mockClear();
    mockGetTimeline.mockClear();
    mockGetCorrelations.mockResolvedValue(CORRELATIONS_RESPONSE);
    mockGetTimeline.mockResolvedValue(TIMELINE_RESPONSE);
  });

  it('switches to timeline tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    const timelineTab = await screen.findByText('Timeline');
    await user.click(timelineTab);
    expect(await screen.findByText('org.add_member')).toBeInTheDocument();
  });

  it('shows timeline events', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    await user.click(await screen.findByText('Timeline'));
    expect(await screen.findByText('org.add_member')).toBeInTheDocument();
    expect(await screen.findByText('repo.create')).toBeInTheDocument();
  });

  it('renders search input', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CrossOrgPage />);
    await user.click(await screen.findByText('Timeline'));
    const input = await screen.findByPlaceholderText('Filter by actor…');
    expect(input).toBeInTheDocument();
  });
});

describe('CrossOrgPage — Error Handling', () => {
  beforeEach(() => {
    mockGetCorrelations.mockClear();
    mockGetTimeline.mockClear();
  });

  it('shows error banner on correlation failure', async () => {
    mockGetCorrelations.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('Failed to load correlations')).toBeInTheDocument();
  });
});
