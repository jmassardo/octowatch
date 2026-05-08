import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MaintenanceBanner } from './MaintenanceBanner';

const mockGetMaintenanceStatus = vi.fn();

vi.mock('../../api/maintenance', () => ({
  getMaintenanceStatus: (...args: unknown[]) => mockGetMaintenanceStatus(...args),
}));

function renderBanner(ui = <MaintenanceBanner />) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('MaintenanceBanner', () => {
  beforeEach(() => {
    vi.useRealTimers();
    mockGetMaintenanceStatus.mockReset();
  });

  it('renders the active maintenance message and metadata', () => {
    renderBanner(
      <MaintenanceBanner
        polling={false}
        status={{
          enabled: true,
          message: 'Deploying upgrades',
          severity: 'critical',
          block_writes: true,
          started_at: '2025-06-10T10:00:00Z',
          estimated_end: '2025-06-10T12:00:00Z',
        }}
      />,
    );

    expect(screen.getByText('Deploying upgrades')).toBeInTheDocument();
    expect(screen.getByText(/write operations are temporarily disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/estimated end:/i)).toBeInTheDocument();
    expect(screen.getByTestId('maintenance-banner')).toHaveAttribute('data-severity', 'critical');
  });

  it('can be dismissed for the current session', async () => {
    const user = userEvent.setup();

    renderBanner(
      <MaintenanceBanner
        polling={false}
        status={{
          enabled: true,
          message: 'Deploying upgrades',
          severity: 'warning',
          block_writes: false,
          started_at: null,
          estimated_end: null,
        }}
      />,
    );

    expect(screen.getByText('Deploying upgrades')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /dismiss maintenance notice/i }));

    expect(screen.queryByText('Deploying upgrades')).not.toBeInTheDocument();
  });

  it('polls for status updates every 30 seconds', async () => {
    mockGetMaintenanceStatus
      .mockResolvedValueOnce({
        enabled: true,
        message: 'First message',
        severity: 'info',
        block_writes: false,
        started_at: null,
        estimated_end: null,
      })
      .mockResolvedValueOnce({
        enabled: true,
        message: 'Updated message',
        severity: 'warning',
        block_writes: true,
        started_at: null,
        estimated_end: null,
      });

    renderBanner(<MaintenanceBanner pollIntervalMs={10} />);

    await waitFor(() => {
      expect(screen.getByText('First message')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText('Updated message')).toBeInTheDocument();
    });
    expect(mockGetMaintenanceStatus).toHaveBeenCalledTimes(2);
  });
});
