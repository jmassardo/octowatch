import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { BacktestPanel } from './BacktestPanel';
import type { RuleResponse } from '../../types/detections';

const mockBacktestRule = vi.fn();

vi.mock('../../api/rules', () => ({
  backtestRule: (...args: unknown[]) => mockBacktestRule(...args),
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

describe('BacktestPanel', () => {
  it('renders date inputs and run button', () => {
    renderWithProviders(<BacktestPanel rule={sampleRule} />);

    expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run backtest/i })).toBeInTheDocument();
  });

  it('shows results after running a backtest', async () => {
    mockBacktestRule.mockResolvedValue({
      matches: [
        {
          event_id: 42,
          timestamp: '2024-07-01T10:00:00Z',
          actor: 'octocat',
          action: 'auth.login',
          org: 'octowatch',
          repo: 'octowatch/frontend',
          matched_conditions: ['action_filters'],
        },
      ],
      total_matches: 1,
      capped: false,
      duration_ms: 25,
      events_scanned: 50,
    });

    const user = userEvent.setup();
    renderWithProviders(<BacktestPanel rule={sampleRule} />);

    await user.click(screen.getByRole('button', { name: /run backtest/i }));

    await waitFor(() => {
      expect(screen.getByText(/1 matches in 50 events scanned \(25 ms\)/i)).toBeInTheDocument();
    });
    expect(screen.getByText('octocat')).toBeInTheDocument();
    expect(screen.getByText('auth.login')).toBeInTheDocument();
  });
});
