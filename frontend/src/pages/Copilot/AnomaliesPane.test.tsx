import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnomaliesPane } from './AnomaliesPane';

describe('AnomaliesPane clickable stats', () => {
  it('renders the anomaly count as clickable', () => {
    render(<AnomaliesPane />);
    const countEl = screen.getByText('3 anomalies');
    expect(countEl).toHaveAttribute('role', 'button');
    expect(countEl).toHaveAttribute('tabIndex', '0');
  });

  it('scrolls to anomaly list when clicking the count', async () => {
    const user = userEvent.setup();
    const scrollMock = vi.fn();
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = scrollMock;

    render(<AnomaliesPane />);
    const countEl = screen.getByText('3 anomalies');
    await user.click(countEl);
    expect(scrollMock).toHaveBeenCalledWith({ behavior: 'smooth' });
  });

  it('renders severity badges as clickable', () => {
    render(<AnomaliesPane />);
    const highBadge = screen.getByText('HIGH').closest('[role="button"]');
    expect(highBadge).toBeTruthy();
    expect(highBadge).toHaveAttribute('tabIndex', '0');
  });

  it('filters anomalies by severity when clicking a badge', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    // Click the HIGH badge to filter
    const highBadge = screen.getByText('HIGH').closest('[role="button"]')!;
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
    render(<AnomaliesPane />);
    const highBadge = screen.getByText('HIGH').closest('[role="button"]')!;
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
    render(<AnomaliesPane />);
    const medBadge = screen.getByText('MEDIUM').closest('[role="button"]')!;
    await user.click(medBadge);
    const clearBtn = screen.getByText('clear');
    expect(clearBtn).toHaveAttribute('role', 'button');
  });

  it('clears filter when clicking the clear link', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    const medBadge = screen.getByText('MEDIUM').closest('[role="button"]')!;
    await user.click(medBadge);
    expect(screen.getByText(/filtered: medium/)).toBeInTheDocument();
    await user.click(screen.getByText('clear'));
    expect(screen.queryByText(/filtered:/)).not.toBeInTheDocument();
  });

  it('renders team names as clickable', () => {
    render(<AnomaliesPane />);
    const backendTeam = screen.getByText('Backend');
    expect(backendTeam).toHaveAttribute('role', 'button');
    expect(backendTeam).toHaveAttribute('tabIndex', '0');
    expect(backendTeam.classList.contains('anomalyTeamClickable')).toBe(true);
  });

  it('opens team modal when clicking a team name', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    await user.click(screen.getByText('Backend'));
    expect(screen.getByText('Backend team — anomaly context')).toBeInTheDocument();
    const dialog = document.querySelector('.dialog')! as HTMLElement;
    expect(within(dialog).getByText(/Copilot Metrics API integration/)).toBeInTheDocument();
  });

  it('opens Platform team modal', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    await user.click(screen.getByText('Platform'));
    expect(screen.getByText('Platform team — anomaly context')).toBeInTheDocument();
  });

  it('closes team modal via close button', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    await user.click(screen.getByText('Backend'));
    expect(screen.getByText('Backend team — anomaly context')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Backend team — anomaly context')).not.toBeInTheDocument();
  });

  it('shows sample data note in team modal', async () => {
    const user = userEvent.setup();
    render(<AnomaliesPane />);
    await user.click(screen.getByText('ML/AI'));
    expect(
      screen.getByText(/Connect the Copilot Metrics API for live per-user data/),
    ).toBeInTheDocument();
  });
});
