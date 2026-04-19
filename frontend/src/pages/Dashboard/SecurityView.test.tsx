import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SecurityView } from './SecurityView';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockGetUnifiedSecurity = vi.fn().mockResolvedValue({
  secret_scanning: { open: 5, resolved: 20, total: 25, bypassed_open: 1 },
  code_scanning: { open: 12, critical: 2, high: 4, medium: 3, low: 3, total: 50 },
  dependabot: {
    open: 8,
    critical: 1,
    high: 3,
    medium: 2,
    low: 2,
    total: 40,
    critical_aging_gt_90d: 0,
  },
  detections: { active: 3, critical: 1, high: 1, medium: 1, low: 0 },
  trend_30d: [],
});

const mockGetSecurityPosture = vi.fn().mockResolvedValue({
  repos_with_secret_scanning: 45,
  repos_with_dependabot: 42,
  repos_with_codeql: 38,
  repos_with_ghas: 50,
  features_disabled_count: 3,
});

const mockListDetections = vi.fn().mockResolvedValue({
  items: [
    {
      id: 101,
      rule_id: 1,
      rule_name: 'Token Abuse',
      rule_version: 1,
      severity: 'critical',
      confidence: 'high',
      confidence_score: 0.95,
      status: 'open',
      title: 'Suspicious PAT usage',
      description: 'desc',
      actor: 'attacker',
      org: 'acme-corp',
      repo: null,
      source_ip: null,
      window_start: null,
      window_end: null,
      event_ids: [1],
      context_data: {},
      triggered_at: '2026-04-15T10:00:00Z',
      assigned_to: null,
      resolved_at: null,
      resolution_note: null,
      tickets: [],
    },
    {
      id: 102,
      rule_id: 2,
      rule_name: 'Branch Override',
      rule_version: 1,
      severity: 'high',
      confidence: 'medium',
      confidence_score: 0.8,
      status: 'open',
      title: 'Branch protection bypass',
      description: 'desc',
      actor: 'dev-user',
      org: 'acme-corp',
      repo: null,
      source_ip: null,
      window_start: null,
      window_end: null,
      event_ids: [2],
      context_data: {},
      triggered_at: '2026-04-14T08:00:00Z',
      assigned_to: null,
      resolved_at: null,
      resolution_note: null,
      tickets: [],
    },
  ],
  total: 2,
  page: 1,
  page_size: 10,
  has_next: false,
});

vi.mock('../../api/healthSignals', () => ({
  getUnifiedSecurity: (...args: unknown[]) => mockGetUnifiedSecurity(...args),
  getSecurityPosture: (...args: unknown[]) => mockGetSecurityPosture(...args),
}));

vi.mock('../../api/detections', () => ({
  listDetections: (...args: unknown[]) => mockListDetections(...args),
}));

describe('SecurityView', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('renders top metric cards with data', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('5')).toBeInTheDocument(); // secret alerts
    expect(screen.getByText('Open secret alerts')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument(); // code scanning
    expect(screen.getByText('Open code scanning alerts')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument(); // dependabot
    expect(screen.getByText('Open Dependabot alerts')).toBeInTheDocument();
  });

  it('renders active threat detections count', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Active threat detections')).toBeInTheDocument();
  });

  it('renders GHAS enabled repos metric', async () => {
    renderWithProviders(<SecurityView />);

    // "50" appears in both GHAS metric card and GHAS coverage card
    const fiftyElements = await screen.findAllByText('50');
    expect(fiftyElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('GHAS enabled repos')).toBeInTheDocument();
  });

  it('renders the threat activity table', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Threat Activity')).toBeInTheDocument();
    expect(screen.getByText('Suspicious PAT usage')).toBeInTheDocument();
    expect(screen.getByText('Branch protection bypass')).toBeInTheDocument();
    expect(screen.getByText('attacker')).toBeInTheDocument();
    // Both detections share 'acme-corp' org, so multiple elements exist
    const acmeElements = screen.getAllByText('acme-corp');
    expect(acmeElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the security feature coverage section', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Security Feature Coverage')).toBeInTheDocument();
    expect(screen.getByText('Secret scanning enabled')).toBeInTheDocument();
    expect(screen.getByText('CodeQL enabled')).toBeInTheDocument();
    expect(screen.getByText('Dependabot enabled')).toBeInTheDocument();
    expect(screen.getByText('GHAS enabled')).toBeInTheDocument();
    expect(screen.getByText('Features disabled')).toBeInTheDocument();
  });

  it('renders features disabled count', async () => {
    renderWithProviders(<SecurityView />);

    await screen.findByText('Features disabled');
    expect(screen.getByText('45')).toBeInTheDocument(); // secret scanning enabled
    expect(screen.getByText('38')).toBeInTheDocument(); // codeql enabled
    expect(screen.getByText('42')).toBeInTheDocument(); // dependabot enabled
  });

  it('navigates to threats page when clicking a threat row', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SecurityView />);

    await screen.findByText('Suspicious PAT usage');

    const row = screen.getByText('Suspicious PAT usage').closest('tr');
    expect(row).toBeTruthy();
    await user.click(row!);

    expect(mockNavigate).toHaveBeenCalledWith('/threats?id=101');
  });

  it('shows empty message when no threats', async () => {
    mockListDetections.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      has_next: false,
    });

    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('No open threats')).toBeInTheDocument();
  });

  it('shows error banner on unified security failure', async () => {
    mockGetUnifiedSecurity.mockRejectedValueOnce(new Error('fail'));
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Could not load security alerts')).toBeInTheDocument();
  });
});
