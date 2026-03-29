import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { TestRuleModal } from './TestRuleModal';
import type { RuleResponse } from '../../types/detections';

const mockTestRule = vi.fn();

vi.mock('../../api/rules', () => ({
  listRules: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 }),
  createRule: vi.fn().mockResolvedValue({}),
  updateRule: vi.fn().mockResolvedValue({}),
  deleteRule: vi.fn().mockResolvedValue(undefined),
  listRuleVersions: vi.fn().mockResolvedValue([]),
  validateRuleConfig: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
  testRule: (...args: unknown[]) => mockTestRule(...args),
}));

const sampleRule: RuleResponse = {
  id: 1,
  name: 'Impossible Travel Login',
  slug: 'impossible-travel',
  description: 'Detect logins from geographically impossible locations',
  category: 'impossible_travel',
  default_severity: 'high',
  default_confidence: 'high',
  logic_type: 'statistical',
  logic_config: { action_filters: ['auth.login'], confidence: 0.5 },
  enabled: true,
  status: 'active',
  version: 2,
  git_commit_sha: null,
  created_by: 'admin',
  updated_by: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-06-15T10:30:00Z',
};

describe('TestRuleModal', () => {
  beforeEach(() => {
    mockTestRule.mockReset();
  });

  it('does not render when rule is null', () => {
    renderWithProviders(<TestRuleModal rule={null} onClose={() => {}} />);
    expect(screen.queryByText(/test rule/i)).not.toBeInTheDocument();
  });

  it('renders modal title with rule name when open', () => {
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);
    expect(screen.getByText(`Test Rule: ${sampleRule.name}`)).toBeInTheDocument();
  });

  it('pre-populates textarea with sample JSON', () => {
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);
    const textarea = screen.getByLabelText(/sample event payload/i) as HTMLTextAreaElement;
    expect(textarea.value).toContain('"action"');
    // Should be valid JSON
    expect(() => JSON.parse(textarea.value)).not.toThrow();
  });

  it('shows Run Test and Close buttons', () => {
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);
    expect(screen.getByRole('button', { name: /run test/i })).toBeInTheDocument();
    // The modal × button also has aria-label="Close", so use getAllByRole
    const closeButtons = screen.getAllByRole('button', { name: /close/i });
    expect(closeButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('calls onClose when Close button is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={onClose} />);
    // Use getByText to target the explicit "Close" button, not the modal × (aria-label="Close")
    await user.click(screen.getByText('Close'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('shows match result after successful test', async () => {
    mockTestRule.mockResolvedValue({
      matched: true,
      reason: 'Event matches all rule conditions',
      matched_fields: ['action', 'confidence'],
    });

    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run test/i }));

    await waitFor(() => {
      expect(screen.getByText('✓ Rule would trigger')).toBeInTheDocument();
    });
    expect(screen.getByText('Event matches all rule conditions')).toBeInTheDocument();
    expect(screen.getByText('Matched fields:')).toBeInTheDocument();
    expect(screen.getByText('action')).toBeInTheDocument();
    expect(screen.getByText('confidence')).toBeInTheDocument();
  });

  it('shows no-match result after test fails to match', async () => {
    mockTestRule.mockResolvedValue({
      matched: false,
      reason: "Event action 'repos.create' does not match any action filter",
      matched_fields: [],
    });

    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run test/i }));

    await waitFor(() => {
      expect(screen.getByText('✗ Rule would not trigger')).toBeInTheDocument();
    });
  });

  it('shows parse error for invalid JSON', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    const textarea = screen.getByLabelText(/sample event payload/i);
    await user.clear(textarea);
    await user.type(textarea, 'not valid json');

    await user.click(screen.getByRole('button', { name: /run test/i }));

    expect(screen.getByText(/invalid json/i)).toBeInTheDocument();
    expect(mockTestRule).not.toHaveBeenCalled();
  });

  it('calls testRule with the rule id and parsed event', async () => {
    mockTestRule.mockResolvedValue({
      matched: true,
      reason: 'Event matches',
      matched_fields: [],
    });

    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run test/i }));

    await waitFor(() => {
      expect(mockTestRule).toHaveBeenCalledOnce();
    });

    const [ruleId, event] = mockTestRule.mock.calls[0];
    expect(ruleId).toBe(sampleRule.id);
    expect(typeof event).toBe('object');
    expect(event).toHaveProperty('action');
  });

  it('shows API error message on failure', async () => {
    mockTestRule.mockRejectedValue(new Error('Network failure'));

    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run test/i }));

    await waitFor(() => {
      expect(screen.getByText(/api error/i)).toBeInTheDocument();
    });
  });

  it('does not show matched_fields list when no fields matched', async () => {
    mockTestRule.mockResolvedValue({
      matched: false,
      reason: 'No match',
      matched_fields: [],
    });

    const user = userEvent.setup();
    renderWithProviders(<TestRuleModal rule={sampleRule} onClose={() => {}} />);

    await user.click(screen.getByRole('button', { name: /run test/i }));

    await waitFor(() => {
      expect(screen.getByText('✗ Rule would not trigger')).toBeInTheDocument();
    });
    expect(screen.queryByText('Matched fields:')).not.toBeInTheDocument();
  });

  it('pre-populates different sample events per category', () => {
    const exfilRule = { ...sampleRule, id: 10, category: 'exfiltration' as const };
    renderWithProviders(<TestRuleModal rule={exfilRule} onClose={() => {}} />);
    const textarea = screen.getByLabelText(/sample event payload/i) as HTMLTextAreaElement;
    const parsed = JSON.parse(textarea.value);
    expect(parsed.action).toBe('repo.clone');
  });
});
