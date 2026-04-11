import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { GovernancePane } from './GovernancePane';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockListPolicies = vi.fn();
const mockListViolations = vi.fn();
const mockUpdatePolicy = vi.fn();

vi.mock('../../api/copilotGovernance', () => ({
  listCopilotPolicies: (...args: unknown[]) => mockListPolicies(...args),
  listCopilotViolations: (...args: unknown[]) => mockListViolations(...args),
  updateCopilotPolicy: (...args: unknown[]) => mockUpdatePolicy(...args),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const POLICIES = [
  {
    id: 1,
    name: 'Seat Utilization Threshold',
    policy_type: 'seat_utilization',
    severity: 'medium',
    enabled: true,
    config: { min_active_percentage: 60 },
    created_by: 'admin',
    created_at: '2024-06-01T10:00:00Z',
    updated_at: '2024-06-01T10:00:00Z',
  },
  {
    id: 2,
    name: 'Language Allow List',
    policy_type: 'language_allowlist',
    severity: 'high',
    enabled: false,
    config: { allowed_languages: ['python', 'typescript'] },
    created_by: 'admin',
    created_at: '2024-06-02T10:00:00Z',
    updated_at: '2024-06-02T10:00:00Z',
  },
];

const VIOLATIONS_RESPONSE = {
  violations: [
    {
      id: 1,
      policy_id: 1,
      policy_name: 'Seat Utilization Threshold',
      severity: 'medium',
      actor: 'jdoe',
      org: 'myorg',
      description: 'Copilot seat inactive for 30 days',
      context_data: {},
      detected_at: '2024-06-07T10:00:00Z',
      status: 'open',
    },
  ],
  total: 1,
};

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('GovernancePane — Policies', () => {
  beforeEach(() => {
    mockListPolicies.mockClear();
    mockListViolations.mockClear();
    mockUpdatePolicy.mockClear();
    mockListPolicies.mockResolvedValue(POLICIES);
    mockListViolations.mockResolvedValue(VIOLATIONS_RESPONSE);
  });

  it('renders policy section title', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Governance Policies')).toBeInTheDocument();
  });

  it('renders policy cards', async () => {
    renderWithProviders(<GovernancePane />);
    const seatMatches = await screen.findAllByText('Seat Utilization Threshold');
    expect(seatMatches.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('Language Allow List')).toBeInTheDocument();
  });

  it('shows active/disabled status', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Active')).toBeInTheDocument();
    expect(await screen.findByText('Disabled')).toBeInTheDocument();
  });

  it('shows enable/disable buttons', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Disable')).toBeInTheDocument();
    expect(await screen.findByText('Enable')).toBeInTheDocument();
  });

  it('calls updatePolicy on toggle', async () => {
    mockUpdatePolicy.mockResolvedValue({});
    const user = userEvent.setup();
    renderWithProviders(<GovernancePane />);
    const disableBtn = await screen.findByText('Disable');
    await user.click(disableBtn);
    expect(mockUpdatePolicy).toHaveBeenCalledWith(1, { enabled: false });
  });

  it('renders empty state when no policies', async () => {
    mockListPolicies.mockResolvedValue([]);
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('No governance policies configured')).toBeInTheDocument();
  });
});

describe('GovernancePane — Violations', () => {
  beforeEach(() => {
    mockListPolicies.mockClear();
    mockListViolations.mockClear();
    mockListPolicies.mockResolvedValue(POLICIES);
    mockListViolations.mockResolvedValue(VIOLATIONS_RESPONSE);
  });

  it('renders violation section title with count', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Policy Violations')).toBeInTheDocument();
    expect(await screen.findByText('(1)')).toBeInTheDocument();
  });

  it('renders violation rows', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Copilot seat inactive for 30 days')).toBeInTheDocument();
  });

  it('shows violation actor', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('jdoe')).toBeInTheDocument();
  });

  it('renders severity filter', async () => {
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByDisplayValue('All severities')).toBeInTheDocument();
  });

  it('renders empty state when no violations', async () => {
    mockListViolations.mockResolvedValue({ violations: [], total: 0 });
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('No violations found')).toBeInTheDocument();
  });
});

describe('GovernancePane — Error Handling', () => {
  beforeEach(() => {
    mockListPolicies.mockClear();
    mockListViolations.mockClear();
  });

  it('shows error banner on policy load failure', async () => {
    mockListPolicies.mockRejectedValue(new Error('Network error'));
    mockListViolations.mockResolvedValue(VIOLATIONS_RESPONSE);
    renderWithProviders(<GovernancePane />);
    expect(await screen.findByText('Failed to load policies')).toBeInTheDocument();
  });
});
