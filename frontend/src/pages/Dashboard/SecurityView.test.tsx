import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { SecurityView } from './SecurityView';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
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

vi.mock('../../api/healthSignals', () => ({
  getUnifiedSecurity: (...args: unknown[]) => mockGetUnifiedSecurity(...args),
  getSecurityPosture: (...args: unknown[]) => mockGetSecurityPosture(...args),
}));

// BarChart uses echarts — mock it to avoid canvas errors in test env
vi.mock('../../components/charts/BarChart', () => ({
  BarChart: () => <div data-testid="bar-chart" />,
}));

describe('SecurityView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('renders GHAS enabled repos metric', async () => {
    renderWithProviders(<SecurityView />);

    const fiftyElements = await screen.findAllByText('50');
    expect(fiftyElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('GHAS enabled repos')).toBeInTheDocument();
  });

  it('renders the alert trend section with a bar chart', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Alert Trend')).toBeInTheDocument();
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
  });

  it('renders the security feature coverage section with gauges', async () => {
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Security Feature Coverage')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Secret Scanning/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /CodeQL/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Dependabot/i })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /GHAS/i })).toBeInTheDocument();
  });

  it('shows error banner on unified security failure', async () => {
    mockGetUnifiedSecurity.mockRejectedValueOnce(new Error('fail'));
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Could not load security alerts')).toBeInTheDocument();
  });

  it('shows error banner on posture failure', async () => {
    mockGetSecurityPosture.mockRejectedValueOnce(new Error('fail'));
    renderWithProviders(<SecurityView />);

    expect(await screen.findByText('Could not load security posture')).toBeInTheDocument();
  });
});
