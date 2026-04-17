import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { MetricsThatMatter } from './MetricsThatMatter';

const mockGetMetricsThatMatter = vi.fn().mockResolvedValue({
  period_days: 30,
  generated_at: '2024-01-15T00:00:00Z',
  shipping_faster: {
    avg_pr_lifecycle_hours: 12.5,
    avg_pr_review_rounds: 1.8,
    deployment_frequency_per_week: 3.2,
    pr_merge_rate_pct: 78.5,
    trend: [{ date: '2024-01-08T00:00:00Z', avg_pr_hours: 12.5, deployments: 3 }],
  },
  shipping_safer: {
    workflow_success_rate_pct: 94.2,
    codeql_alerts_opened: 5,
    codeql_alerts_closed: 7,
    secret_alerts_opened: 2,
    secret_alerts_resolved: 1,
    branch_protection_compliance_pct: 85.0,
    change_failure_rate_pct: 3.1,
    trend: [{ date: '2024-01-08T00:00:00Z', success_rate: 94.2, codeql_delta: -2, secret_delta: 1 }],
  },
  shipping_cheaper: {
    failed_run_waste_pct: 8.3,
    rerun_rate_pct: 5.1,
    automation_merge_rate_pct: 32.0,
    avg_pr_review_rounds: 1.8,
    top_wasteful_workflows: [{ workflow: 'long-test-suite-name', waste_pct: 22.5 }],
    trend: [{ date: '2024-01-08T00:00:00Z', failed_waste_pct: 8.3, rerun_rate: 5.1 }],
  },
});

vi.mock('../../api/executive', () => ({
  getMetricsThatMatter: (...args: unknown[]) => mockGetMetricsThatMatter(...args),
}));

vi.mock('../../components/charts/LineAreaChart', () => ({
  LineAreaChart: () => <div data-testid="sparkline" />,
}));

describe('MetricsThatMatter', () => {
  it('renders three column headers', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      expect(screen.getByText('Shipping Faster')).toBeInTheDocument();
      expect(screen.getByText('Shipping Safer')).toBeInTheDocument();
      expect(screen.getByText('Shipping Cheaper')).toBeInTheDocument();
    });
  });

  it('displays faster metrics', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      expect(screen.getByText('12.5h')).toBeInTheDocument();
      expect(screen.getByText('3.2/wk')).toBeInTheDocument();
      expect(screen.getByText('79%')).toBeInTheDocument();
    });
  });

  it('displays safer metrics', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      expect(screen.getByText('94.2%')).toBeInTheDocument();
    });
  });

  it('displays cheaper metrics', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      expect(screen.getByText('8.3%')).toBeInTheDocument();
    });
  });

  it('shows null values as dash', async () => {
    mockGetMetricsThatMatter.mockResolvedValueOnce({
      period_days: 7,
      generated_at: '2024-01-15T00:00:00Z',
      shipping_faster: {
        avg_pr_lifecycle_hours: null,
        avg_pr_review_rounds: null,
        deployment_frequency_per_week: null,
        pr_merge_rate_pct: null,
        trend: [],
      },
      shipping_safer: {
        workflow_success_rate_pct: null,
        codeql_alerts_opened: 0,
        codeql_alerts_closed: 0,
        secret_alerts_opened: 0,
        secret_alerts_resolved: 0,
        branch_protection_compliance_pct: null,
        change_failure_rate_pct: null,
        trend: [],
      },
      shipping_cheaper: {
        failed_run_waste_pct: null,
        rerun_rate_pct: null,
        automation_merge_rate_pct: null,
        avg_pr_review_rounds: null,
        top_wasteful_workflows: [],
        trend: [],
      },
    });

    renderWithProviders(<MetricsThatMatter period={7} />);
    await waitFor(() => {
      const nullElements = screen.getAllByTitle('No merged PRs found in this period');
      expect(nullElements.length).toBeGreaterThan(0);
    });
  });

  it('renders sparkline charts', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      const charts = screen.getAllByTestId('sparkline');
      expect(charts.length).toBeGreaterThan(0);
    });
  });

  it('shows section title', async () => {
    renderWithProviders(<MetricsThatMatter period={30} />);
    await waitFor(() => {
      expect(screen.getByText('Metrics That Matter')).toBeInTheDocument();
    });
  });
});
