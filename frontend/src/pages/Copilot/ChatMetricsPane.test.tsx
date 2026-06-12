import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { ChatMetricsPane } from './ChatMetricsPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetCopilotChatMetrics = vi.fn();

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotChatMetrics: (...args: unknown[]) => mockGetCopilotChatMetrics(...args),
}));

describe('ChatMetricsPane', () => {
  beforeEach(() => {
    mockGetCopilotChatMetrics.mockResolvedValue({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      total_interactions: [800, 850, 900],
      code_actions: [200, 210, 220],
      active_chat_users: [95, 100, 105],
      action_rate_pct: [25.0, 24.7, 24.4],
    });
  });

  it('renders summary stats', async () => {
    renderWithProviders(<ChatMetricsPane />);
    expect(await screen.findByText('Total Interactions (28d)')).toBeInTheDocument();
    expect(screen.getByText('Code Actions (28d)')).toBeInTheDocument();
    expect(screen.getByText('Peak Active Chat Users')).toBeInTheDocument();
  });

  it('renders daily interactions chart', async () => {
    renderWithProviders(<ChatMetricsPane />);
    expect(await screen.findByText('Daily Chat Interactions & Code Actions')).toBeInTheDocument();
  });

  it('renders active chat users chart', async () => {
    renderWithProviders(<ChatMetricsPane />);
    expect(await screen.findByText('Daily active chat users')).toBeInTheDocument();
  });

  it('renders action rate chart', async () => {
    renderWithProviders(<ChatMetricsPane />);
    expect(await screen.findByText('Daily action rate')).toBeInTheDocument();
  });
});
