import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
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
      event_count: 42,
      distinct_actions: 8,
      first_seen: '2024-06-01T10:00:00Z',
      last_seen: '2024-06-07T15:00:00Z',
      risk_score: 75,
    },
    {
      actor: 'asmith',
      orgs: ['org-alpha', 'org-gamma'],
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

  it('renders correlation cards', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('jdoe')).toBeInTheDocument();
    expect(await screen.findByText('asmith')).toBeInTheDocument();
  });

  it('shows risk badge on correlation card', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('High (75)')).toBeInTheDocument();
    expect(await screen.findByText('Low (30)')).toBeInTheDocument();
  });

  it('shows org tags', async () => {
    renderWithProviders(<CrossOrgPage />);
    const orgAlphaTags = await screen.findAllByText('org-alpha');
    expect(orgAlphaTags.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('org-beta')).toBeInTheDocument();
  });

  it('shows event count', async () => {
    renderWithProviders(<CrossOrgPage />);
    expect(await screen.findByText('42 events')).toBeInTheDocument();
  });

  it('shows total actors count badge', async () => {
    renderWithProviders(<CrossOrgPage />);
    // The tab badge shows the total count from the API response (total: 2)
    expect(await screen.findByText('2')).toBeInTheDocument();
  });

  it('renders empty state when no correlations', async () => {
    mockGetCorrelations.mockResolvedValue({ correlations: [], total: 0 });
    renderWithProviders(<CrossOrgPage />);
    expect(
      await screen.findByText('No cross-org correlations found in the selected time window'),
    ).toBeInTheDocument();
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
    // After switching to timeline tab, timeline events are rendered
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
    // Switch to timeline tab to make the filter input visible
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
