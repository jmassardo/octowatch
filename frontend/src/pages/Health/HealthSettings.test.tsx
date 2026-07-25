import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HealthSettingsPage } from './HealthSettings';

const mockNavigate = vi.fn();
const mockMutate = vi.fn();
let mockMutationPending = false;

vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}));

let mockQueryReturn: {
  data: Record<string, unknown> | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => mockQueryReturn,
    useMutation: (opts: { onSuccess?: () => void }) => ({
      mutate: (...args: unknown[]) => {
        mockMutate(...args);
        opts.onSuccess?.();
      },
      isPending: mockMutationPending,
    }),
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  };
});

vi.mock('../../api/healthSignals', () => ({
  getHealthSettings: vi.fn(),
  updateHealthSettings: vi.fn(),
}));

function renderPage() {
  return render(<HealthSettingsPage />);
}

describe('HealthSettingsPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockMutate.mockClear();
    mockMutationPending = false;
    mockQueryReturn = {
      data: {
        staleRepoDays: 90,
        stalePrDays: 30,
        unreviewedDependabotDays: 60,
        ciSkippedConsecutive: 10,
        dormantMemberDays: 90,
        patNoExpiryFlag: true,
        patStaleDays: 90,
        outsideCollabFlag: true,
        licenseUtilizationPct: 80,
        ghostMemberCost: 19,
        escalateCriticalDays: 60,
        escalateStaleReposDays: 180,
        escalateDormantDays: 180,
        escalationDestination: 'Detection queue (internal)',
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  });

  /* ---- Loading / Error states ---- */

  it('shows loading spinner while loading settings', () => {
    mockQueryReturn = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPage();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('shows error banner on load failure', () => {
    mockQueryReturn = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPage();
    expect(screen.getByText('Failed to load health settings')).toBeInTheDocument();
  });

  /* ---- Header ---- */

  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Health Settings')).toBeInTheDocument();
    expect(
      screen.getByText(/Configure thresholds, escalation behavior, and data source options/),
    ).toBeInTheDocument();
  });

  it('renders back button that navigates to /health', async () => {
    const user = userEvent.setup();
    renderPage();
    const backBtn = screen.getByRole('button', { name: /Back/ });
    await user.click(backBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/health');
  });

  /* ---- Settings groups ---- */

  it('renders all settings group titles', () => {
    renderPage();
    expect(screen.getByText('Repository Health Thresholds')).toBeInTheDocument();
    expect(screen.getByText('Access & Identity Thresholds')).toBeInTheDocument();
    expect(screen.getByText('License Health')).toBeInTheDocument();
    expect(screen.getByText('Alerting Escalation (Future)')).toBeInTheDocument();
    expect(screen.getByText('Baseline & Data Sources')).toBeInTheDocument();
  });

  /* ---- Settings values populated from query data ---- */

  it('renders stale repo threshold with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('Stale repo threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders stale PR threshold with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('Stale PR threshold in days');
    expect(input).toHaveValue(30);
  });

  it('renders Dependabot alerts threshold with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('Unreviewed Dependabot alerts threshold in days');
    expect(input).toHaveValue(60);
  });

  it('renders CI skipped workflow signal with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('CI skipped workflow consecutive count');
    expect(input).toHaveValue(10);
  });

  it('renders dormant member threshold with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('Dormant member threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders PAT no-expiry toggle defaulting to on', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles[0]).toHaveAttribute('aria-checked', 'true');
  });

  it('renders PAT stale threshold with value from query data', () => {
    renderPage();
    const input = screen.getByLabelText('PAT stale threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders outside collaborator toggle defaulting to on', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles[1]).toHaveAttribute('aria-checked', 'true');
  });

  it('renders license utilization threshold from query data', () => {
    renderPage();
    const input = screen.getByLabelText('License utilization warning threshold percentage');
    expect(input).toHaveValue(80);
  });

  it('renders ghost member cost from query data', () => {
    renderPage();
    const input = screen.getByLabelText('Ghost member cost in dollars');
    expect(input).toHaveValue(19);
  });

  it('renders escalation thresholds from query data', () => {
    renderPage();
    expect(screen.getByLabelText('Escalate critical signals after days')).toHaveValue(60);
    expect(screen.getByLabelText('Escalate stale repos after days')).toHaveValue(180);
    expect(screen.getByLabelText('Escalate dormant members after days')).toHaveValue(180);
  });

  it('renders escalation destination select with options', () => {
    renderPage();
    const select = screen.getByLabelText('Escalation destination');
    expect(select).toHaveValue('Detection queue (internal)');
    const options = within(select).getAllByRole('option');
    expect(options).toHaveLength(3);
  });

  /* ---- Save triggers mutation ---- */

  it('save button triggers mutation', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: /Save settings/ }));
    expect(mockMutate).toHaveBeenCalledWith(expect.objectContaining({ staleRepoDays: 90 }));
  });

  it('shows toast after saving', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: /Save settings/ }));
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved successfully');
  });

  it('save button shows "Saving…" when pending', () => {
    mockMutationPending = true;
    renderPage();
    expect(screen.getByRole('button', { name: /Saving/ })).toBeInTheDocument();
  });

  /* ---- Reset restores defaults ---- */

  it('resets all values to defaults and shows toast', async () => {
    const user = userEvent.setup();
    renderPage();

    const staleRepoInput = screen.getByLabelText('Stale repo threshold in days');
    await user.clear(staleRepoInput);
    await user.type(staleRepoInput, '200');
    expect(staleRepoInput).toHaveValue(200);

    await user.click(screen.getByRole('button', { name: /Reset to defaults/ }));
    expect(staleRepoInput).toHaveValue(90);
    expect(screen.getByRole('status')).toHaveTextContent('Settings reset to defaults');
  });

  /* ---- Form controls ---- */

  it('updates number input when user types a new value', async () => {
    const user = userEvent.setup();
    renderPage();
    const input = screen.getByLabelText('Stale repo threshold in days');
    await user.clear(input);
    await user.type(input, '120');
    expect(input).toHaveValue(120);
  });

  it('toggles PAT no-expiry flag off and back on', async () => {
    const user = userEvent.setup();
    renderPage();
    const toggles = screen.getAllByRole('switch');
    const patToggle = toggles[0];

    expect(patToggle).toHaveAttribute('aria-checked', 'true');
    await user.click(patToggle);
    expect(patToggle).toHaveAttribute('aria-checked', 'false');
    await user.click(patToggle);
    expect(patToggle).toHaveAttribute('aria-checked', 'true');
  });

  it('changes escalation destination via select', async () => {
    const user = userEvent.setup();
    renderPage();
    const select = screen.getByLabelText('Escalation destination');
    await user.selectOptions(select, 'PagerDuty');
    expect(select).toHaveValue('PagerDuty');
  });

  /* ---- Accessibility ---- */

  it('all number inputs have aria-labels', () => {
    renderPage();
    const inputs = screen.getAllByRole('spinbutton');
    for (const input of inputs) {
      expect(input).toHaveAttribute('aria-label');
    }
  });

  it('toggles have role="switch" with aria-checked', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles).toHaveLength(2);
    for (const toggle of toggles) {
      expect(toggle).toHaveAttribute('aria-checked');
    }
  });

  /* ---- Baseline & Data Sources ---- */

  it('renders baseline import date and integrations link', () => {
    renderPage();
    expect(screen.getByText('Mar 20, 2026')).toBeInTheDocument();
    const intButton = screen.getByRole('button', { name: /Integrations/ });
    expect(intButton).toBeInTheDocument();
  });

  it('navigates to /integrations when clicking integrations button', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: /Integrations/ }));
    expect(mockNavigate).toHaveBeenCalledWith('/integrations');
  });

  it('renders active status label for audit log signals', () => {
    renderPage();
    expect(screen.getByText('active')).toBeInTheDocument();
  });
});
