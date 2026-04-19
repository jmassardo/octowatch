import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnomaliesPane } from './AnomaliesPane';

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
});
