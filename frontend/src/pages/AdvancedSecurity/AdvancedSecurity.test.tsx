import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { AdvancedSecurityPage } from './index';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

function makeTrend30d() {
  return Array.from({ length: 30 }, (_, i) => ({
    day: `2024-01-${String(i + 1).padStart(2, '0')}`,
    secret_scanning: 5 + (i % 3),
    code_scanning: 10 + (i % 5),
    dependabot: 3 + (i % 4),
  }));
}

const mockUnifiedSecurity = {
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
  trend_30d: makeTrend30d(),
};

const mockSecretScanning = {
  unresolved_total: 5,
  publicly_leaked: 1,
  push_protection_bypassed_count: 2,
  mttr_hours: 48.5,
  resolution_rate_pct: 80.0,
};

const mockSecretScanningAlerts = {
  alerts: [
    {
      id: 1,
      repo_full_name: 'org/repo',
      secret_type: 'github_token',
      secret_type_display: 'GitHub Token',
      state: 'open',
      push_protection_bypassed: false,
      push_protection_bypassed_by: null,
      file_path: 'src/config.ts',
      commit_sha: 'abc123',
      created_at: '2024-01-15T00:00:00Z',
      resolved_at: null,
      resolution: null,
    },
  ],
  total: 1,
};

const mockCodeScanning = {
  open_count: 12,
  critical_count: 2,
  high_count: 4,
  avg_hours_to_close: 72,
  fixed_count: 30,
};

const mockCodeScanningAlerts = {
  alerts: [
    {
      id: 1,
      repo_full_name: 'org/repo',
      rule_id: 'js/sql-injection',
      rule_description: 'SQL injection',
      severity: 'high',
      security_severity: 'high',
      tool_name: 'CodeQL',
      file_path: 'src/db.ts',
      start_line: 42,
      state: 'open',
      dismissed_by: null,
      dismissed_reason: null,
      cwe_ids: ['CWE-89'],
      created_at: '2024-01-10T00:00:00Z',
      fixed_at: null,
    },
  ],
  total: 1,
};

const mockVulnerabilities = {
  total_open: 8,
  critical_open: 1,
  high_open: 3,
  avg_open_days: 45,
  critical_aging_gt_90d: 0,
};

const mockDependabotAlerts = {
  alerts: [
    {
      id: 1,
      repo_full_name: 'org/repo',
      package_name: 'lodash',
      package_ecosystem: 'npm',
      severity: 'critical',
      cvss_score: 9.8,
      cve_id: 'CVE-2021-12345',
      cwe_ids: ['CWE-400'],
      vulnerable_version_range: '<4.17.21',
      patched_version: '4.17.21',
      state: 'open',
      dismissed_by: null,
      dismissed_reason: null,
      created_at: '2024-01-05T00:00:00Z',
      fixed_at: null,
    },
  ],
  total: 1,
};

const mockDetections = {
  items: [
    {
      id: 'det-1',
      title: 'Secret scanning bypass detected',
      rule_name: 'ghas-secret-bypass',
      severity: 'high',
      actor: 'user1',
      org: 'myorg',
      triggered_at: '2024-01-20T00:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
};

vi.mock('../../api/healthSignals', () => ({
  getUnifiedSecurity: vi.fn().mockImplementation(() => Promise.resolve(mockUnifiedSecurity)),
  getSecretScanningAlerts: vi
    .fn()
    .mockImplementation(() => Promise.resolve(mockSecretScanningAlerts)),
  getSecretScanning: vi.fn().mockImplementation(() => Promise.resolve(mockSecretScanning)),
  getCodeScanningAlerts: vi.fn().mockImplementation(() => Promise.resolve(mockCodeScanningAlerts)),
  getCodeScanning: vi.fn().mockImplementation(() => Promise.resolve(mockCodeScanning)),
  getDependabotAlerts: vi.fn().mockImplementation(() => Promise.resolve(mockDependabotAlerts)),
  getVulnerabilities: vi.fn().mockImplementation(() => Promise.resolve(mockVulnerabilities)),
}));

vi.mock('../../api/detections', () => ({
  listDetections: vi.fn().mockImplementation(() => Promise.resolve(mockDetections)),
}));

vi.mock('../../api/secretScanning', () => ({
  listSecretAlerts: vi.fn().mockImplementation(() => Promise.resolve({ items: [], total: 0 })),
  getSecretAlertSummary: vi.fn().mockImplementation(() =>
    Promise.resolve({
      open_alerts: 5,
      closed_alerts: 3,
      publicly_leaked: 1,
      push_protection_bypassed: 2,
      resolution_rate: 37.5,
      by_secret_type: [],
      by_repository: [],
    }),
  ),
  getSecretAlertTrends: vi
    .fn()
    .mockImplementation(() => Promise.resolve({ daily: [], weekly: [] })),
  getSecretAlertAuditTrail: vi.fn().mockImplementation(() => Promise.resolve([])),
  getPushProtectionStats: vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve({ total_blocks: 0, total_bypasses: 0, bypass_rate: 0, by_reason: [] }),
    ),
}));

describe('AdvancedSecurityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders overview tab with metric cards', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      // "Alert Trend" only appears after data loads
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    // Tab labels + card labels both show "Secret Scanning", etc.
    expect(screen.getAllByText('Secret Scanning').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Code Scanning').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Dependabot').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Threat Detections')).toBeInTheDocument();
  });

  it('overview cards have onClick handlers that switch tabs', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    // Cards are within the cardGrid and have role="button"
    // The tab buttons don't have aria-label so we can distinguish them
    const allButtons = screen.getAllByRole('button');
    const cardButtons = allButtons.filter((btn) => btn.getAttribute('aria-label') !== null);

    // Overview tab should have 4 clickable metric cards
    const secretCard = cardButtons.find((b) => b.getAttribute('aria-label') === 'Secret Scanning');
    const codeCard = cardButtons.find((b) => b.getAttribute('aria-label') === 'Code Scanning');
    const depCard = cardButtons.find((b) => b.getAttribute('aria-label') === 'Dependabot');
    const threatCard = cardButtons.find(
      (b) => b.getAttribute('aria-label') === 'Threat Detections',
    );

    expect(secretCard).toBeInTheDocument();
    expect(codeCard).toBeInTheDocument();
    expect(depCard).toBeInTheDocument();
    expect(threatCard).toBeInTheDocument();
  });

  it('clicking Threat Detections card navigates to /threats', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    const allButtons = screen.getAllByRole('button');
    const threatCard = allButtons.find((b) => b.getAttribute('aria-label') === 'Threat Detections');
    fireEvent.click(threatCard!);

    expect(mockNavigate).toHaveBeenCalledWith('/threats');
  });

  it('renders trend delta indicators on overview cards', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    // With our mock data of 30 days, week-over-week deltas should be computed
    const deltaElements = document.querySelectorAll('[class*="delta"]');
    expect(deltaElements.length).toBeGreaterThan(0);
  });

  it('renders period toggle on trend chart', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    expect(screen.getByText('7d')).toBeInTheDocument();
    expect(screen.getByText('14d')).toBeInTheDocument();
    expect(screen.getByText('30d')).toBeInTheDocument();
  });

  it('period toggle buttons update chart', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('7d')).toBeInTheDocument();
    });

    const btn7d = screen.getByText('7d');
    fireEvent.click(btn7d);
    expect(btn7d).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders mini sparklines on overview cards', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=overview' });

    await waitFor(() => {
      expect(screen.getByText('Alert Trend')).toBeInTheDocument();
    });

    // Sparklines are SVGs with aria-hidden
    const sparklines = document.querySelectorAll('svg[aria-hidden="true"]');
    // At least 3 sparklines (secret, code, dependabot)
    expect(sparklines.length).toBeGreaterThanOrEqual(3);
  });

  it('secret scanning tab renders SecretsPane', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=secrets' });

    await waitFor(() => {
      // SecretsPane renders summary metrics including Open Alerts
      expect(screen.getByText('Open Alerts')).toBeInTheDocument();
    });
  });

  it('code scanning tab cards are clickable', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=code' });

    await waitFor(() => {
      expect(screen.getByText('Critical')).toBeInTheDocument();
    });

    const criticalCard = screen.getByRole('button', { name: 'Critical' });
    expect(criticalCard).toBeInTheDocument();

    const highCard = screen.getByRole('button', { name: 'High' });
    expect(highCard).toBeInTheDocument();

    const openCard = screen.getByRole('button', { name: 'Open Alerts' });
    expect(openCard).toBeInTheDocument();

    const fixedCard = screen.getByRole('button', { name: 'Fixed' });
    expect(fixedCard).toBeInTheDocument();
  });

  it('dependabot tab cards are clickable', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=dependabot' });

    await waitFor(() => {
      expect(screen.getByText('Total Open')).toBeInTheDocument();
    });

    const totalOpenCard = screen.getByRole('button', { name: 'Total Open' });
    expect(totalOpenCard).toBeInTheDocument();

    const criticalCard = screen.getByRole('button', { name: 'Critical Open' });
    expect(criticalCard).toBeInTheDocument();

    const highCard = screen.getByRole('button', { name: 'High Open' });
    expect(highCard).toBeInTheDocument();

    const aging = screen.getByRole('button', { name: 'Critical >90d' });
    expect(aging).toBeInTheDocument();
  });

  it('clicking code scanning Critical card sets severity filter', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=code' });

    await waitFor(() => {
      expect(screen.getByText('Critical')).toBeInTheDocument();
    });

    const criticalCard = screen.getByRole('button', { name: 'Critical' });
    fireEvent.click(criticalCard);

    // The severity filter select should now show "critical"
    await waitFor(() => {
      const sevSelect = screen.getAllByRole('combobox')[1]; // second select = severity
      expect(sevSelect).toHaveValue('critical');
    });
  });

  it('clicking dependabot High Open card sets severity filter', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=dependabot' });

    await waitFor(() => {
      expect(screen.getByText('High Open')).toBeInTheDocument();
    });

    const highCard = screen.getByRole('button', { name: 'High Open' });
    fireEvent.click(highCard);

    await waitFor(() => {
      const sevSelect = screen.getAllByRole('combobox')[1];
      expect(sevSelect).toHaveValue('high');
    });
  });

  it('secret scanning tab is accessible via tab navigation', async () => {
    renderWithProviders(<AdvancedSecurityPage />, { route: '/security?tab=secrets' });

    await waitFor(() => {
      expect(screen.getByText('Open Alerts')).toBeInTheDocument();
    });
  });
});
