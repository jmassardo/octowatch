import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { RuleAnalytics } from './RuleAnalytics';
import type { RuleResponse } from '../../types/detections';

const mockGetRuleAnalytics = vi.fn();

vi.mock('../../api/rules', () => ({
  getRuleAnalytics: (...args: unknown[]) => mockGetRuleAnalytics(...args),
}));

vi.mock('../../components/charts/LineAreaChart', () => ({
  LineAreaChart: () => <div data-testid="line-area-chart">Line chart</div>,
}));

const sampleRule: RuleResponse = {
  id: 1,
  name: 'Impossible Travel Login',
  slug: 'impossible-travel',
  description: 'Detect suspicious travel patterns',
  category: 'impossible_travel',
  default_severity: 'high',
  default_confidence: 'high',
  logic_type: 'statistical',
  logic_config: {},
  enabled: true,
  mode: 'active',
  status: 'active',
  version: 1,
  git_commit_sha: null,
  created_by: 'admin',
  updated_by: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

describe('RuleAnalytics', () => {
  it('renders metric cards, chart, and top tables', async () => {
    mockGetRuleAnalytics.mockResolvedValue({
      total_detections: 18,
      detections_by_day: [
        { date: '2024-07-01', count: 3 },
        { date: '2024-07-02', count: 5 },
      ],
      avg_detections_per_day: 1.8,
      false_positive_rate: 0.15,
      mean_time_to_triage_hours: 4.5,
      top_actors: [{ name: 'octocat', count: 6 }],
      top_repos: [{ name: 'octowatch/frontend', count: 4 }],
      top_actions: [{ name: 'auth.login', count: 8 }],
    });

    renderWithProviders(<RuleAnalytics rule={sampleRule} />);

    expect(await screen.findByText('Total Detections')).toBeInTheDocument();
    expect(screen.getByText('Avg/Day')).toBeInTheDocument();
    expect(screen.getByText('FP Rate')).toBeInTheDocument();
    expect(screen.getByText('MTTT (hours)')).toBeInTheDocument();
    expect(screen.getByTestId('line-area-chart')).toBeInTheDocument();
    expect(screen.getByText('Top Actors')).toBeInTheDocument();
    expect(screen.getByText('Top Repositories')).toBeInTheDocument();
    expect(screen.getByText('Top Actions')).toBeInTheDocument();
    expect(screen.getByText('octocat')).toBeInTheDocument();
    expect(screen.getByText('octowatch/frontend')).toBeInTheDocument();
    expect(screen.getByText('auth.login')).toBeInTheDocument();
  });
});
