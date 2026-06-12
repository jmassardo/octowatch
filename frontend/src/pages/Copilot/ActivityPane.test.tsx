import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { ActivityPane } from './ActivityPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetCopilotActivity = vi.fn();

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotActivity: (...args: unknown[]) => mockGetCopilotActivity(...args),
}));

describe('ActivityPane', () => {
  beforeEach(() => {
    mockGetCopilotActivity.mockResolvedValue({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      ide_dau: [120, 125, 130],
      ide_wau: [450, 460, 470],
      completions_count: [3400, 3500, 3600],
      completions_accepted: [1200, 1300, 1400],
      acceptance_rate_pct: [35.2, 37.1, 38.9],
      chat_requests_per_user: [4.2, 4.5, 4.8],
      requests_per_mode: {
        dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
        completions: [3400, 3500, 3600],
        chat: [800, 850, 900],
        dotcom_chat: [200, 210, 220],
        pr: [50, 55, 60],
      },
    });
  });

  it('renders IDE daily active users chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('IDE daily active users')).toBeInTheDocument();
  });

  it('renders IDE weekly active users chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('IDE weekly active users')).toBeInTheDocument();
  });

  it('renders code completions chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('Code completions')).toBeInTheDocument();
  });

  it('renders acceptance rate chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('Code completions acceptance rate')).toBeInTheDocument();
  });

  it('renders chat requests per user chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('Average chat requests per active user')).toBeInTheDocument();
  });

  it('renders requests per mode chart', async () => {
    renderWithProviders(<ActivityPane />);
    expect(await screen.findByText('Requests per chat mode')).toBeInTheDocument();
  });
});
