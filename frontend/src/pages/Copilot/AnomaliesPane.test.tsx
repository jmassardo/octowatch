import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnomaliesPane } from './AnomaliesPane';
import { getCopilotAnomalies } from '../../api/copilotMetrics';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotAnomalies: vi.fn().mockResolvedValue({
    anomalies: [
      {
        id: 1,
        severity: 'high' as const,
        title: 'Sudden drop in acceptance rate',
        description:
          'Acceptance rate dropped 15% in Backend team over the last 48 hours. This correlates with a new linting config deployment.',
        timestamp: '2 hours ago',
        team: 'Backend',
        affected_count: 42,
      },
      {
        id: 2,
        severity: 'medium' as const,
        title: 'Unusual seat churn detected',
        description:
          '12 seats were revoked and re-assigned within 24 hours in the Platform org. This may indicate a provisioning script issue.',
        timestamp: '6 hours ago',
        team: 'Platform',
      },
      {
        id: 3,
        severity: 'low' as const,
        title: 'Knowledge base usage spike',
        description:
          'Knowledge base queries increased 340% in ML/AI team. Likely related to onboarding of 5 new team members.',
        timestamp: '1 day ago',
        team: 'ML/AI',
        affected_count: 5,
      },
    ],
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AnomaliesPane />
    </QueryClientProvider>,
  );
}

describe('AnomaliesPane clickable stats', () => {
  it('renders the anomaly count as clickable', async () => {
    renderPane();
    const countEl = await screen.findByText('3 anomalies');
    expect(countEl).toHaveAttribute('role', 'button');
    expect(countEl).toHaveAttribute('tabIndex', '0');
  });

  it('scrolls to anomaly list when clicking the count', async () => {
    const user = userEvent.setup();
    const scrollMock = vi.fn();
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = scrollMock;

    renderPane();
    const countEl = await screen.findByText('3 anomalies');
    await user.click(countEl);
    expect(scrollMock).toHaveBeenCalledWith({ behavior: 'smooth' });
  });

  it('renders severity badges as clickable', async () => {
    renderPane();
    const highBadge = (await screen.findByText('HIGH')).closest('[role="button"]');
    expect(highBadge).toBeTruthy();
    expect(highBadge).toHaveAttribute('tabIndex', '0');
  });

  it('filters anomalies by severity when clicking a badge', async () => {
    const user = userEvent.setup();
    renderPane();
    // Click the HIGH badge to filter
    const highBadge = (await screen.findByText('HIGH')).closest('[role="button"]')!;
    await user.click(highBadge);

    // Should show the filter indicator
    expect(screen.getByText(/filtered: high/)).toBeInTheDocument();

    // Should only show the high severity anomaly
    expect(screen.getByText('Sudden drop in acceptance rate')).toBeInTheDocument();
    expect(screen.queryByText('Unusual seat churn detected')).not.toBeInTheDocument();
    expect(screen.queryByText('Knowledge base usage spike')).not.toBeInTheDocument();
  });

  it('clears severity filter when clicking the same badge again', async () => {
    const user = userEvent.setup();
    renderPane();
    const highBadge = (await screen.findByText('HIGH')).closest('[role="button"]')!;
    await user.click(highBadge);
    expect(screen.getByText(/filtered: high/)).toBeInTheDocument();

    // Click HIGH badge again to clear filter
    const highBadgeAgain = screen.getByText('HIGH').closest('[role="button"]')!;
    await user.click(highBadgeAgain);
    expect(screen.queryByText(/filtered:/)).not.toBeInTheDocument();
    // All anomalies should be visible
    expect(screen.getByText('Sudden drop in acceptance rate')).toBeInTheDocument();
    expect(screen.getByText('Unusual seat churn detected')).toBeInTheDocument();
  });

  it('shows clear link when filter is active', async () => {
    const user = userEvent.setup();
    renderPane();
    const medBadge = (await screen.findByText('MEDIUM')).closest('[role="button"]')!;
    await user.click(medBadge);
    const clearBtn = screen.getByText('clear');
    expect(clearBtn).toHaveAttribute('role', 'button');
  });

  it('clears filter when clicking the clear link', async () => {
    const user = userEvent.setup();
    renderPane();
    const medBadge = (await screen.findByText('MEDIUM')).closest('[role="button"]')!;
    await user.click(medBadge);
    expect(screen.getByText(/filtered: medium/)).toBeInTheDocument();
    await user.click(screen.getByText('clear'));
    expect(screen.queryByText(/filtered:/)).not.toBeInTheDocument();
  });

  it('renders team names as clickable', async () => {
    renderPane();
    const backendTeam = await screen.findByText('Backend');
    expect(backendTeam).toHaveAttribute('role', 'button');
    expect(backendTeam).toHaveAttribute('tabIndex', '0');
    expect(backendTeam.classList.contains('anomalyTeamClickable')).toBe(true);
  });

  it('opens team modal when clicking a team name', async () => {
    const user = userEvent.setup();
    renderPane();
    await user.click(await screen.findByText('Backend'));
    expect(screen.getByText('Backend team — anomaly context')).toBeInTheDocument();
    const dialog = document.querySelector('.dialog')! as HTMLElement;
    expect(within(dialog).getByText(/Copilot Metrics API integration/)).toBeInTheDocument();
  });

  it('opens Platform team modal', async () => {
    const user = userEvent.setup();
    renderPane();
    await user.click(await screen.findByText('Platform'));
    expect(screen.getByText('Platform team — anomaly context')).toBeInTheDocument();
  });

  it('closes team modal via close button', async () => {
    const user = userEvent.setup();
    renderPane();
    await user.click(await screen.findByText('Backend'));
    expect(screen.getByText('Backend team — anomaly context')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Backend team — anomaly context')).not.toBeInTheDocument();
  });

  it('shows team anomaly details in modal', async () => {
    const user = userEvent.setup();
    renderPane();
    await user.click(await screen.findByText('ML/AI'));
    expect(screen.getByText(/ML\/AI team — anomaly context/)).toBeInTheDocument();
  });

  it('shows affected count when present on an anomaly', async () => {
    renderPane();
    await screen.findByText('Sudden drop in acceptance rate');
    // The high severity anomaly has affected_count: 42
    expect(screen.getByText('42')).toBeInTheDocument();
    // The low severity anomaly has affected_count: 5
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('displays Affected label for anomalies with affected_count', async () => {
    renderPane();
    await screen.findByText('Sudden drop in acceptance rate');
    const affectedLabels = screen.getAllByText('Affected:');
    // Two anomalies have affected_count (id 1 and 3)
    expect(affectedLabels.length).toBe(2);
  });
});

describe('AnomaliesPane detection rules', () => {
  it('shows collapsible detection rules section when anomalies exist', async () => {
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules \(6 active\)/ });
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands rules table when clicking the toggle', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Acceptance Rate Drop')).toBeInTheDocument();
    expect(screen.getByText('Active User Count Change')).toBeInTheDocument();
    expect(screen.getByText('Feature Usage Spike')).toBeInTheDocument();
    expect(screen.getByText('Sudden Active User Drop')).toBeInTheDocument();
    expect(screen.getByText('Model Switching Detection')).toBeInTheDocument();
    expect(screen.getByText('Bulk Policy Changes')).toBeInTheDocument();
  });

  it('shows Create Custom Rule button when rules are expanded', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    expect(screen.getByRole('button', { name: /Create Custom Rule/ })).toBeInTheDocument();
  });

  it('does not show Create Custom Rule button when rules are collapsed', async () => {
    renderPane();
    await screen.findByRole('button', { name: /Detection Rules/ });
    expect(screen.queryByRole('button', { name: /Create Custom Rule/ })).not.toBeInTheDocument();
  });

  it('shows enabled status labels with tooltip', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    const enabledLabels = screen.getAllByText('Enabled');
    expect(enabledLabels.length).toBe(6);
    // Check that the parent span has the tooltip
    const firstLabel = enabledLabels[0].closest('[title]');
    expect(firstLabel).toHaveAttribute('title', 'Custom rules coming soon');
  });

  it('shows detection rules section when no anomalies exist', async () => {
    vi.mocked(getCopilotAnomalies).mockResolvedValueOnce({ anomalies: [] });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <AnomaliesPane />
      </QueryClientProvider>,
    );
    // Should show the no anomalies message
    const noAnomalies = await screen.findByText(/No anomalies detected/);
    expect(noAnomalies).toBeInTheDocument();
    // Detection rules toggle should still be visible
    expect(screen.getByRole('button', { name: /Detection Rules/ })).toBeInTheDocument();
  });
});

describe('AnomaliesPane custom rule modal', () => {
  it('opens the custom rule modal when clicking Create Custom Rule', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));
    expect(screen.getByText('Create Custom Detection Rule')).toBeInTheDocument();
  });

  it('renders all form fields in the modal', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));

    expect(screen.getByLabelText('Rule name')).toBeInTheDocument();
    expect(screen.getByLabelText('Metric to monitor')).toBeInTheDocument();
    expect(screen.getByLabelText('Condition')).toBeInTheDocument();
    expect(screen.getByLabelText('Threshold value')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Severity/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Rule' })).toBeInTheDocument();
  });

  it('shows future release message when saving a custom rule', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <AnomaliesPane />
      </QueryClientProvider>,
    );

    // Wait for data to load and expand rules
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);

    // Open the custom rule modal
    const createBtn = await screen.findByRole('button', { name: /Create Custom Rule/ });
    await user.click(createBtn);

    // Verify the modal is open - use findBy to wait for portal render
    await screen.findByText('Create Custom Detection Rule');

    // Fill form fields using fireEvent to avoid focus/portal timing issues
    const nameInput = screen.getByLabelText('Rule name');
    fireEvent.change(nameInput, { target: { value: 'My rule' } });

    const thresholdInput = screen.getByLabelText('Threshold value');
    fireEvent.change(thresholdInput, { target: { value: '25' } });

    await user.click(screen.getByRole('button', { name: 'Save Rule' }));

    expect(
      await screen.findByText(/Custom detection rules will be available in a future release/),
    ).toBeInTheDocument();
  });

  it('has metric dropdown with expected options', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));

    const metricSelect = screen.getByLabelText('Metric to monitor');
    const options = within(metricSelect).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([
      'Acceptance rate',
      'Active users',
      'Feature usage',
      'Model distribution',
      'Custom',
    ]);
  });

  it('has condition dropdown with expected options', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));

    const conditionSelect = screen.getByLabelText('Condition');
    const options = within(conditionSelect).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['drops below', 'rises above', 'changes by']);
  });

  it('has severity radio buttons with high, medium, low', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));

    expect(screen.getByRole('radio', { name: 'high' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'medium' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'low' })).toBeInTheDocument();
    // Medium should be checked by default
    expect(screen.getByRole('radio', { name: 'medium' })).toBeChecked();
  });

  it('closes the modal when clicking close', async () => {
    const user = userEvent.setup();
    renderPane();
    const toggle = await screen.findByRole('button', { name: /Detection Rules/ });
    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Create Custom Rule/ }));
    expect(screen.getByText('Create Custom Detection Rule')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Create Custom Detection Rule')).not.toBeInTheDocument();
  });
});
