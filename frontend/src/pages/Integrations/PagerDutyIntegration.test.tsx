import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { PagerDutyIntegration } from './PagerDutyIntegration';
import type { PagerDutyConfigResponse } from '../../api/pagerduty';

const mockGetPagerDutyConfig = vi.fn<() => Promise<PagerDutyConfigResponse>>();
const mockUpdatePagerDutyConfig = vi.fn();
const mockTestPagerDutyConnection = vi.fn();

vi.mock('../../api/pagerduty', () => ({
  getPagerDutyConfig: (...args: unknown[]) => mockGetPagerDutyConfig(...(args as [])),
  updatePagerDutyConfig: (...args: unknown[]) => mockUpdatePagerDutyConfig(...args),
  testPagerDutyConnection: (...args: unknown[]) => mockTestPagerDutyConnection(...(args as [])),
}));

const config: PagerDutyConfigResponse = {
  routing_key_configured: true,
  routing_key_masked: 'abcd********wxyz',
  severity_mapping: {
    critical: 'critical',
    high: 'error',
    medium: 'warning',
    low: 'info',
    info: 'info',
  },
  notification_settings: {
    detections: true,
    sync_errors: true,
    system_health: false,
    threat_intel: true,
  },
  auto_resolve: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetPagerDutyConfig.mockResolvedValue(config);
  mockUpdatePagerDutyConfig.mockResolvedValue(config);
  mockTestPagerDutyConnection.mockResolvedValue({
    ok: true,
    message: 'Test event sent successfully',
  });
});

describe('PagerDutyIntegration', () => {
  it('renders PagerDuty configuration from the API', async () => {
    renderWithProviders(<PagerDutyIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/critical severity mapping/i)).toHaveValue('critical');
    });

    expect(screen.getByRole('heading', { name: /pagerduty integration/i })).toBeInTheDocument();
    expect(
      screen.getByRole('checkbox', {
        name: /resolve incidents when a detection is marked resolved/i,
      }),
    ).toBeChecked();
  });

  it('saves updated PagerDuty settings', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PagerDutyIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/medium severity mapping/i)).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText(/medium severity mapping/i), 'error');
    await user.click(screen.getByRole('checkbox', { name: /enable system health/i }));
    await user.click(screen.getByRole('button', { name: /save pagerduty settings/i }));

    await waitFor(() => {
      expect(mockUpdatePagerDutyConfig).toHaveBeenCalledWith({
        severity_mapping: {
          critical: 'critical',
          high: 'error',
          medium: 'error',
          low: 'info',
          info: 'info',
        },
        notification_settings: {
          detections: true,
          sync_errors: true,
          system_health: true,
          threat_intel: true,
        },
        auto_resolve: true,
        routing_key: undefined,
      });
    });
  });

  it('tests the PagerDuty connection and shows status', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PagerDutyIntegration />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => {
      expect(mockTestPagerDutyConnection).toHaveBeenCalledOnce();
    });

    expect(screen.getByText('Test event sent successfully')).toBeInTheDocument();
  });
});
