import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { AgentActivityPane } from './AgentActivityPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetCopilotAgentActivity = vi.fn();

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotAgentActivity: (...args: unknown[]) => mockGetCopilotAgentActivity(...args),
}));

describe('AgentActivityPane', () => {
  beforeEach(() => {
    mockGetCopilotAgentActivity.mockResolvedValue({
      dates: ['2026-06-01', '2026-06-02', '2026-06-03'],
      daily_lines_added: [5000, 5200, 5400],
      daily_lines_accepted: [3000, 3200, 3400],
      lines_by_mode: {
        completions: [4000, 4100, 4200],
        chat: [800, 850, 900],
        pr: [200, 250, 300],
      },
      lines_by_model: [
        { model: 'gpt-4o', lines_added: 25000, lines_accepted: 15000 },
        { model: 'claude-3.5', lines_added: 18000, lines_accepted: 12000 },
      ],
      lines_by_language: [
        { language: 'TypeScript', lines_added: 20000, lines_accepted: 12000 },
        { language: 'Python', lines_added: 15000, lines_accepted: 9000 },
      ],
    });
  });

  it('renders summary stats', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Lines Suggested (28d)')).toBeInTheDocument();
    expect(screen.getByText('Lines Accepted (28d)')).toBeInTheDocument();
    expect(screen.getByText('Line Acceptance Rate')).toBeInTheDocument();
  });

  it('renders daily lines chart', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Daily lines suggested & accepted')).toBeInTheDocument();
  });

  it('renders code changes by mode chart', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Code changes by mode')).toBeInTheDocument();
  });

  it('renders lines by model chart', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Lines added by model')).toBeInTheDocument();
  });

  it('renders lines by language chart', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Lines added by language')).toBeInTheDocument();
  });

  it('renders feature activity over time chart', async () => {
    renderWithProviders(<AgentActivityPane />);
    expect(await screen.findByText('Feature activity over time')).toBeInTheDocument();
  });
});
