import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { PRMetricsPane } from './PRMetricsPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetCopilotPRMetrics = vi.fn();

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotPRMetrics: (...args: unknown[]) => mockGetCopilotPRMetrics(...args),
}));

describe('PRMetricsPane', () => {
  beforeEach(() => {
    mockGetCopilotPRMetrics.mockResolvedValue({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      pr_activity: [10, 12, 14],
      pr_contributions: [50, 55, 60],
      review_suggestions: [30, 35, 40],
    });
  });

  it('renders summary stats', async () => {
    renderWithProviders(<PRMetricsPane />);
    expect(await screen.findByText('PR Active Users (28d)')).toBeInTheDocument();
    expect(screen.getByText('PR Summaries Generated')).toBeInTheDocument();
    expect(screen.getByText('Review Suggestions Accepted')).toBeInTheDocument();
  });

  it('renders PR activity chart', async () => {
    renderWithProviders(<PRMetricsPane />);
    expect(await screen.findByText('Pull Request Activity Over Time')).toBeInTheDocument();
  });

  it('renders PR contributions chart', async () => {
    renderWithProviders(<PRMetricsPane />);
    expect(await screen.findByText('Copilot PR contributions')).toBeInTheDocument();
  });

  it('renders review suggestions chart', async () => {
    renderWithProviders(<PRMetricsPane />);
    expect(await screen.findByText('Review suggestions')).toBeInTheDocument();
  });
});
