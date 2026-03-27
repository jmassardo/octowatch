import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OverviewPane } from './OverviewPane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockSeatBuckets = [
  {
    bucket: '2024-01-14',
    active_seat_count: 120,
    provisioned_seat_count: 180,
    utilization_pct: 66.7,
  },
  {
    bucket: '2024-01-15',
    active_seat_count: 124,
    provisioned_seat_count: 186,
    utilization_pct: 66.7,
  },
];

const mockCopilotBuckets = [
  { bucket: '2024-01-14', seats_assigned: 5, seats_revoked: 1, seats_net: 4, policy_change_count: 0 },
  { bucket: '2024-01-15', seats_assigned: 3, seats_revoked: 2, seats_net: 1, policy_change_count: 0 },
];

function renderPane() {
  return render(
    <OverviewPane
      seatBuckets={mockSeatBuckets}
      copilotBuckets={mockCopilotBuckets}
      isLoading={false}
      isError={false}
      onRetry={() => {}}
    />,
  );
}

function getClickableStats(): HTMLElement[] {
  return screen.getAllByRole('button').filter(
    (el) => el.classList.contains('clickableStat'),
  );
}

describe('OverviewPane clickable stats', () => {
  it('renders the waste alert with clickable dollar amount', () => {
    renderPane();
    const stats = getClickableStats();
    const dollarBtn = stats.find((el) => el.textContent?.includes('/month'));
    expect(dollarBtn).toBeTruthy();
  });

  it('opens seat utilization breakdown modal when clicking dollar amount', async () => {
    const user = userEvent.setup();
    renderPane();
    const stats = getClickableStats();
    const dollarBtn = stats.find((el) => el.textContent?.includes('/month'))!;
    await user.click(dollarBtn);
    expect(screen.getByText('Seat utilization breakdown')).toBeInTheDocument();
    // Verify modal has a table with expected columns
    const dialog = document.querySelector('.dialog')!;
    expect(within(dialog as HTMLElement).getByText('Inactive')).toBeInTheDocument();
    expect(within(dialog as HTMLElement).getByText('Cost ($/mo)')).toBeInTheDocument();
  });

  it('opens seat utilization modal when clicking inactive seat count', async () => {
    const user = userEvent.setup();
    renderPane();
    const stats = getClickableStats();
    const seatBtn = stats.find((el) => el.textContent?.includes('seats'))!;
    await user.click(seatBtn);
    expect(screen.getByText('Seat utilization breakdown')).toBeInTheDocument();
  });

  it('closes the seat utilization modal via close button', async () => {
    const user = userEvent.setup();
    renderPane();
    const stats = getClickableStats();
    const dollarBtn = stats.find((el) => el.textContent?.includes('/month'))!;
    await user.click(dollarBtn);
    expect(screen.getByText('Seat utilization breakdown')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Seat utilization breakdown')).not.toBeInTheDocument();
  });

  it('opens correlation modal when clicking "38 seats"', async () => {
    const user = userEvent.setup();
    renderPane();
    const seatsBtn = screen.getByText('38 seats');
    expect(seatsBtn).toHaveAttribute('role', 'button');
    await user.click(seatsBtn);
    expect(
      screen.getByText('Correlation: Active seats with low acceptance'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Connect the Copilot Metrics API for live per-user data/),
    ).toBeInTheDocument();
  });

  it('opens correlation modal when clicking "23%"', async () => {
    const user = userEvent.setup();
    renderPane();
    const pctBtn = screen.getByText('23%');
    expect(pctBtn).toHaveAttribute('role', 'button');
    await user.click(pctBtn);
    expect(
      screen.getByText('Correlation: Acceptance rate vs cycle time'),
    ).toBeInTheDocument();
  });

  it('makes language bar rows clickable with proper accessibility', () => {
    renderPane();
    const tsRow = screen.getByText('TypeScript').closest('[role="button"]');
    expect(tsRow).toBeTruthy();
    expect(tsRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens language modal when clicking a language row', async () => {
    const user = userEvent.setup();
    renderPane();
    const tsRow = screen.getByText('TypeScript').closest('[role="button"]')!;
    await user.click(tsRow);
    expect(screen.getByText('TypeScript — Acceptance rate details')).toBeInTheDocument();
    expect(screen.getByText(/acceptance rate of/)).toBeInTheDocument();
  });

  it('opens language modal for different languages', async () => {
    const user = userEvent.setup();
    renderPane();
    const pyRow = screen.getByText('Python').closest('[role="button"]')!;
    await user.click(pyRow);
    expect(screen.getByText('Python — Acceptance rate details')).toBeInTheDocument();
  });
});
