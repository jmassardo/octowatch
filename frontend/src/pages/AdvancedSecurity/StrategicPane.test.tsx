import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { AdvancedSecurityPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockNavigate = vi.fn();
let mockTab = 'strategic';

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ tab: mockTab }),
  };
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

const mockSecretScanningAlerts = { alerts: [], total: 0 };
const mockCodeScanning = {
  open_count: 12,
  critical_count: 2,
  high_count: 4,
  avg_hours_to_close: 72,
  fixed_count: 30,
};
const mockCodeScanningAlerts = { alerts: [], total: 0 };
const mockVulnerabilities = {
  total_open: 8,
  critical_open: 1,
  high_open: 3,
  avg_open_days: 45,
  critical_aging_gt_90d: 0,
};
const mockDependabotAlerts = { alerts: [], total: 0 };
const mockDetections = { items: [], total: 0, page: 1, page_size: 50 };

// Strategic mocks matching actual backend response shapes
const mockSecurityScore = {
  score: 78.5,
  components: [
    {
      name: 'Coverage',
      score: 85.0,
      weight: 30,
      description: 'Repository adoption of GHAS features.',
    },
    {
      name: 'MTTR',
      score: 75.0,
      weight: 25,
      description: 'Average time to remediate resolved alerts.',
    },
    {
      name: 'Alert Volume',
      score: 80.0,
      weight: 20,
      description: 'Open alert load relative to repository count.',
    },
    {
      name: 'Aging',
      score: 70.0,
      weight: 15,
      description: 'Share of open alerts older than 30 days.',
    },
    { name: 'Trend', score: 60.0, weight: 10, description: 'Recent MTTR direction.' },
  ],
  suggestions: [
    { name: 'Aging', impact: 450, suggestion: 'Burn down findings older than 30 days.' },
    { name: 'Trend', impact: 400, suggestion: 'Reverse MTTR deterioration.' },
  ],
};

const mockMttrTrends = {
  current_mttr_hours: 48.0,
  previous_mttr_hours: 72.0,
  trend_pct: -33.33,
  by_severity: [
    { severity: 'critical', mttr_hours: 24.0, sample_size: 5 },
    { severity: 'high', mttr_hours: 48.0, sample_size: 10 },
  ],
  time_series: [
    { date: '2024-01-15', mttr_hours: 40.0 },
    { date: '2024-01-16', mttr_hours: 50.0 },
  ],
  by_tool: [
    { tool: 'code_scanning', mttr_hours: 36.0 },
    { tool: 'secret_scanning', mttr_hours: 12.0 },
    { tool: 'dependabot', mttr_hours: 60.0 },
  ],
};

const mockCoverageGrowth = {
  total_repos: 100,
  feature_coverage: {
    ghas: { repos: 80, pct: 80.0 },
    code_scanning: { repos: 80, pct: 80.0 },
    secret_scanning: { repos: 90, pct: 90.0 },
    dependabot: { repos: 85, pct: 85.0 },
    push_protection: { repos: 70, pct: 70.0 },
  },
  time_series: [
    {
      date: '2024-01-01',
      ghas_pct: 70.0,
      code_scanning_pct: 70.0,
      secret_scanning_pct: 80.0,
      dependabot_pct: 75.0,
      push_protection_pct: 60.0,
      ghas_repos: 70,
      code_scanning_repos: 70,
      secret_scanning_repos: 80,
      dependabot_repos: 75,
      push_protection_repos: 60,
    },
  ],
  uncovered_repos: [
    { repo_full_name: 'test-org/repo1', missing_features: ['code_scanning', 'dependabot'] },
    { repo_full_name: 'test-org/repo2', missing_features: ['secret_scanning'] },
  ],
};

const mockAlertAging = {
  age_buckets: [
    { bucket: '<7d', total_count: 10, critical_count: 2, high_count: 3 },
    { bucket: '7-30d', total_count: 8, critical_count: 1, high_count: 2 },
    { bucket: '30-90d', total_count: 5, critical_count: 0, high_count: 1 },
    { bucket: '>90d', total_count: 3, critical_count: 1, high_count: 0 },
  ],
  oldest_critical: [
    {
      tool: 'code_scanning',
      alert_number: 42,
      repo_full_name: 'test-org/repo1',
      created_at: '2023-06-01T00:00:00Z',
      severity: 'critical',
      age_days: 200,
      rule_info: 'sql-injection',
      rule_description: 'SQL injection vulnerability',
    },
  ],
  burndown_projection: {
    current_open: 26,
    avg_close_rate_per_week: 5.0,
    weeks_to_zero: 5.2,
    time_series: [
      { week: 1, projected_open: 21 },
      { week: 2, projected_open: 16 },
      { week: 3, projected_open: 11 },
      { week: 4, projected_open: 6 },
      { week: 5, projected_open: 1 },
    ],
  },
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
  getSecurityScore: vi.fn().mockImplementation(() => Promise.resolve(mockSecurityScore)),
  getMttrTrends: vi.fn().mockImplementation(() => Promise.resolve(mockMttrTrends)),
  getCoverageGrowth: vi.fn().mockImplementation(() => Promise.resolve(mockCoverageGrowth)),
  getAlertAging: vi.fn().mockImplementation(() => Promise.resolve(mockAlertAging)),
}));

vi.mock('../../api/detections', () => ({
  listDetections: vi.fn().mockImplementation(() => Promise.resolve(mockDetections)),
}));

describe('StrategicPane', () => {
  beforeEach(() => {
    mockTab = 'strategic';
    vi.clearAllMocks();
  });

  it('renders the Strategic tab label in the tab bar', async () => {
    mockTab = 'overview';
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/overview',
    });
    await waitFor(() => {
      expect(screen.getByText('Strategic')).toBeInTheDocument();
    });
  });

  it('renders executive summary metric cards when strategic tab is active', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText('Security Score')).toBeInTheDocument();
    });
    expect(screen.getAllByText('MTTR').length).toBeGreaterThan(0);
    expect(screen.getByText('Critical/High Open')).toBeInTheDocument();
    expect(screen.getByText('GHAS Coverage')).toBeInTheDocument();
    expect(screen.getByText('Avg Alert Age')).toBeInTheDocument();
  });

  it('renders security score breakdown section', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText('Security Score Breakdown')).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Overall Score/)).toBeInTheDocument();
    expect(screen.getByText("What's Dragging Your Score Down")).toBeInTheDocument();
  });

  it('renders MTTR trend section with period toggle', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText(/MTTR Trend/)).toBeInTheDocument();
    });
    const periodBtns = screen.getAllByRole('button');
    const mttrPeriodBtns = periodBtns.filter(
      (b) => b.textContent === '7d' || b.textContent === '30d' || b.textContent === '90d',
    );
    expect(mttrPeriodBtns.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByLabelText('Filter by severity')).toBeInTheDocument();
  });

  it('renders coverage section with feature data', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText(/Security Coverage/)).toBeInTheDocument();
    });
    expect(screen.getAllByText('test-org/repo1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('test-org/repo2').length).toBeGreaterThan(0);
  });

  it('renders alert aging and burndown section', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText(/Alert Aging/)).toBeInTheDocument();
    });
    expect(screen.getByText('Oldest Critical/High Alerts')).toBeInTheDocument();
    expect(screen.getByText('sql-injection')).toBeInTheDocument();
    expect(screen.getByText(/Current open: 26/)).toBeInTheDocument();
  });

  it('renders score value from API', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      expect(screen.getByText('79')).toBeInTheDocument();
    });
  });

  it('renders MTTR value from API', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      // 48 hours = 2d
      expect(screen.getByText('2d')).toBeInTheDocument();
    });
  });

  it('renders critical/high count from aging data', async () => {
    renderWithProviders(<AdvancedSecurityPage />, {
      routePath: '/advanced-security/:tab',
      route: '/advanced-security/strategic',
    });
    await waitFor(() => {
      // Sum of critical_count + high_count: (2+3) + (1+2) + (0+1) + (1+0) = 10
      expect(screen.getByText('10')).toBeInTheDocument();
    });
  });
});
