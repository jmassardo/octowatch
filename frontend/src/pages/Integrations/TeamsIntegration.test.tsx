import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { TeamsIntegration } from './TeamsIntegration';
import type { TeamsConfigResponse } from '../../api/teams';

const mockGetTeamsConfig = vi.fn<() => Promise<TeamsConfigResponse>>();
const mockUpdateTeamsConfig = vi.fn();
const mockTestTeamsConnection = vi.fn();

vi.mock('../../api/teams', () => ({
  getTeamsConfig: (...args: unknown[]) => mockGetTeamsConfig(...(args as [])),
  updateTeamsConfig: (...args: unknown[]) => mockUpdateTeamsConfig(...args),
  testTeamsConnection: (...args: unknown[]) => mockTestTeamsConnection(...args),
}));

const config: TeamsConfigResponse = {
  channel_webhook_configured: {
    default: true,
    detections: true,
    sync_errors: false,
    system_health: false,
    threat_intel: true,
  },
  channel_webhooks_masked: {
    default: 'https://o*******1234',
    detections: 'https://d*******5678',
    sync_errors: null,
    system_health: null,
    threat_intel: 'https://t*******9999',
  },
  source_mappings: {
    detections: 'detections',
    sync_errors: 'default',
    system_health: 'default',
    threat_intel: 'threat_intel',
  },
  notification_settings: {
    detections: true,
    sync_errors: true,
    system_health: false,
    threat_intel: true,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetTeamsConfig.mockResolvedValue(config);
  mockUpdateTeamsConfig.mockResolvedValue(config);
  mockTestTeamsConnection.mockResolvedValue({
    ok: true,
    channel: 'detections',
    message: 'Test message sent successfully',
  });
});

describe('TeamsIntegration', () => {
  it('renders Teams configuration from the API', async () => {
    renderWithProviders(<TeamsIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/detections channel mapping/i)).toHaveValue('detections');
    });

    expect(
      screen.getByRole('heading', { name: /microsoft teams integration/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/default channel webhook/i)).toHaveAttribute(
      'placeholder',
      'https://o*******1234',
    );
  });

  it('saves updated Teams settings', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TeamsIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/system health channel mapping/i)).toBeInTheDocument();
    });

    await user.type(
      screen.getByLabelText(/system health channel webhook/i),
      'https://example.test/system-health',
    );
    await user.selectOptions(
      screen.getByLabelText(/system health channel mapping/i),
      'system_health',
    );
    await user.click(screen.getByRole('checkbox', { name: /enable system health/i }));
    await user.click(screen.getByRole('button', { name: /save teams settings/i }));

    await waitFor(() => {
      expect(mockUpdateTeamsConfig).toHaveBeenCalledWith({
        channel_webhooks: {
          default: '',
          detections: '',
          sync_errors: '',
          system_health: 'https://example.test/system-health',
          threat_intel: '',
        },
        source_mappings: {
          detections: 'detections',
          sync_errors: 'default',
          system_health: 'system_health',
          threat_intel: 'threat_intel',
        },
        notification_settings: {
          detections: true,
          sync_errors: true,
          system_health: true,
          threat_intel: true,
        },
        clear_channels: [],
      });
    });
  });

  it('tests the Teams connection and shows status', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TeamsIntegration />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /test message/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /test message/i }));

    await waitFor(() => {
      expect(mockTestTeamsConnection).toHaveBeenCalledWith('detections');
    });

    expect(screen.getByText('Test message sent successfully')).toBeInTheDocument();
  });
});
