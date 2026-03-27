import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HealthSettingsPage } from './HealthSettings';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

function renderPage() {
  return render(<HealthSettingsPage />);
}

describe('HealthSettingsPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  /* ---- Header ---- */

  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Health Settings')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Configure thresholds, escalation behavior, and data source options/,
      ),
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

  /* ---- Repository Health Thresholds ---- */

  it('renders stale repo threshold with default value of 90', () => {
    renderPage();
    const input = screen.getByLabelText('Stale repo threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders stale PR threshold with default value of 30', () => {
    renderPage();
    const input = screen.getByLabelText('Stale PR threshold in days');
    expect(input).toHaveValue(30);
  });

  it('renders Dependabot alerts threshold with default value of 60', () => {
    renderPage();
    const input = screen.getByLabelText('Unreviewed Dependabot alerts threshold in days');
    expect(input).toHaveValue(60);
  });

  it('renders CI skipped workflow signal with default value of 10', () => {
    renderPage();
    const input = screen.getByLabelText('CI skipped workflow consecutive count');
    expect(input).toHaveValue(10);
  });

  /* ---- Access & Identity Thresholds ---- */

  it('renders dormant member threshold with default value of 90', () => {
    renderPage();
    const input = screen.getByLabelText('Dormant member threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders PAT no-expiry toggle defaulting to on', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles[0]).toHaveAttribute('aria-checked', 'true');
  });

  it('renders PAT stale threshold with default value of 90', () => {
    renderPage();
    const input = screen.getByLabelText('PAT stale threshold in days');
    expect(input).toHaveValue(90);
  });

  it('renders outside collaborator toggle defaulting to on', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles[1]).toHaveAttribute('aria-checked', 'true');
  });

  /* ---- License Health ---- */

  it('renders license utilization threshold with default value of 80', () => {
    renderPage();
    const input = screen.getByLabelText('License utilization warning threshold percentage');
    expect(input).toHaveValue(80);
  });

  it('renders ghost member cost with default value of 19', () => {
    renderPage();
    const input = screen.getByLabelText('Ghost member cost in dollars');
    expect(input).toHaveValue(19);
  });

  /* ---- Alerting Escalation ---- */

  it('renders informational banner in escalation section', () => {
    renderPage();
    expect(
      screen.getByText(/Health signals are/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/informational only/),
    ).toBeInTheDocument();
  });

  it('renders escalation thresholds with default values', () => {
    renderPage();
    const critical = screen.getByLabelText('Escalate critical signals after days');
    expect(critical).toHaveValue(60);
    const staleRepos = screen.getByLabelText('Escalate stale repos after days');
    expect(staleRepos).toHaveValue(180);
    const dormant = screen.getByLabelText('Escalate dormant members after days');
    expect(dormant).toHaveValue(180);
  });

  it('renders escalation destination select with options', () => {
    renderPage();
    const select = screen.getByLabelText('Escalation destination');
    expect(select).toHaveValue('Detection queue (internal)');
    const options = within(select).getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveTextContent('Detection queue (internal)');
    expect(options[1]).toHaveTextContent('Slack — #security-alerts');
    expect(options[2]).toHaveTextContent('PagerDuty');
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

  /* ---- User interactions ---- */

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

    // Initially on
    expect(patToggle).toHaveAttribute('aria-checked', 'true');

    // Click to turn off
    await user.click(patToggle);
    expect(patToggle).toHaveAttribute('aria-checked', 'false');

    // Click to turn back on
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

  /* ---- Save & Reset ---- */

  it('renders save and reset buttons', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /Save settings/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reset to defaults/ })).toBeInTheDocument();
  });

  it('shows toast and logs when saving', async () => {
    const user = userEvent.setup();
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    renderPage();

    await user.click(screen.getByRole('button', { name: /Save settings/ }));

    expect(consoleSpy).toHaveBeenCalledWith(
      'Health settings saved:',
      expect.objectContaining({ staleRepoDays: 90 }),
    );
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved successfully');
  });

  it('resets all values to defaults and shows toast', async () => {
    const user = userEvent.setup();
    renderPage();

    // Change a value
    const staleRepoInput = screen.getByLabelText('Stale repo threshold in days');
    await user.clear(staleRepoInput);
    await user.type(staleRepoInput, '200');
    expect(staleRepoInput).toHaveValue(200);

    // Reset
    await user.click(screen.getByRole('button', { name: /Reset to defaults/ }));

    // Value should be back to default
    expect(staleRepoInput).toHaveValue(90);
    expect(screen.getByRole('status')).toHaveTextContent('Settings reset to defaults');
  });

  it('saves modified settings correctly', async () => {
    const user = userEvent.setup();
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    renderPage();

    // Modify stale PR threshold
    const stalePrInput = screen.getByLabelText('Stale PR threshold in days');
    await user.clear(stalePrInput);
    await user.type(stalePrInput, '45');

    // Modify ghost member cost
    const ghostInput = screen.getByLabelText('Ghost member cost in dollars');
    await user.clear(ghostInput);
    await user.type(ghostInput, '25');

    // Save
    await user.click(screen.getByRole('button', { name: /Save settings/ }));

    expect(consoleSpy).toHaveBeenCalledWith(
      'Health settings saved:',
      expect.objectContaining({
        stalePrDays: 45,
        ghostMemberCost: 25,
      }),
    );
  });

  /* ---- Accessibility ---- */

  it('all number inputs have aria-labels', () => {
    renderPage();
    const inputs = screen.getAllByRole('spinbutton');
    for (const input of inputs) {
      expect(input).toHaveAttribute('aria-label');
    }
  });

  it('select has an aria-label', () => {
    renderPage();
    const select = screen.getByRole('combobox');
    expect(select).toHaveAttribute('aria-label', 'Escalation destination');
  });

  it('toggles have role="switch" with aria-checked', () => {
    renderPage();
    const toggles = screen.getAllByRole('switch');
    expect(toggles).toHaveLength(2);
    for (const toggle of toggles) {
      expect(toggle).toHaveAttribute('aria-checked');
    }
  });
});
