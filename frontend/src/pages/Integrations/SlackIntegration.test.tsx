import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SlackIntegration } from './SlackIntegration';
import type { SlackConfigResponse } from '../../api/slack';

const mockGetSlackConfig = vi.fn<() => Promise<SlackConfigResponse>>();
const mockUpdateSlackConfig = vi.fn();
const mockTestSlackConnection = vi.fn();

vi.mock('../../api/slack', () => ({
  getSlackConfig: (...args: unknown[]) => mockGetSlackConfig(...(args as [])),
  updateSlackConfig: (...args: unknown[]) => mockUpdateSlackConfig(...args),
  testSlackConnection: (...args: unknown[]) => mockTestSlackConnection(...(args as [])),
}));

const config: SlackConfigResponse = {
  bot_token_configured: true,
  signing_secret_configured: true,
  bot_token_masked: 'xoxb********1234',
  signing_secret_masked: 'sign********5678',
  default_channel: '#security-alerts',
  channel_mappings: {
    detections: '#detections',
    sync_errors: '#sync-alerts',
    system_health: '#platform-health',
    threat_intel: '#threat-intel',
  },
  notification_settings: {
    detections: true,
    sync_errors: true,
    system_health: false,
    threat_intel: true,
  },
  installation_url: 'https://api.slack.com/apps',
  installation_instructions: ['Create a Slack app', 'Configure request URLs'],
  commands: ['/octowatch status', '/octowatch threats'],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetSlackConfig.mockResolvedValue(config);
  mockUpdateSlackConfig.mockResolvedValue(config);
  mockTestSlackConnection.mockResolvedValue({
    ok: true,
    channel: '#security-alerts',
    message: 'Test message sent successfully',
  });
});

describe('SlackIntegration', () => {
  it('renders Slack configuration from the API', async () => {
    renderWithProviders(<SlackIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/default channel/i)).toHaveValue('#security-alerts');
    });

    expect(screen.getByText(/slack integration/i)).toBeInTheDocument();
    expect(screen.getByLabelText('Detections channel')).toHaveValue('#detections');
    expect(screen.getByRole('link', { name: /slack app installation guide/i })).toHaveAttribute(
      'href',
      'https://api.slack.com/apps',
    );
  });

  it('saves updated Slack settings', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SlackIntegration />);

    await waitFor(() => {
      expect(screen.getByLabelText(/default channel/i)).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/default channel/i));
    await user.type(screen.getByLabelText(/default channel/i), '#soc-room');
    await user.clear(screen.getByLabelText('System health channel'));
    await user.type(screen.getByLabelText('System health channel'), '#ops-alerts');
    await user.click(screen.getByRole('button', { name: /save slack settings/i }));

    await waitFor(() => {
      expect(mockUpdateSlackConfig).toHaveBeenCalledWith({
        default_channel: '#soc-room',
        channel_mappings: {
          detections: '#detections',
          sync_errors: '#sync-alerts',
          system_health: '#ops-alerts',
          threat_intel: '#threat-intel',
        },
        notification_settings: {
          detections: true,
          sync_errors: true,
          system_health: false,
          threat_intel: true,
        },
        bot_token: undefined,
        signing_secret: undefined,
      });
    });
  });

  it('tests the Slack connection and shows status', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SlackIntegration />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => {
      expect(mockTestSlackConnection).toHaveBeenCalledOnce();
    });

    expect(screen.getByText('Test message sent successfully')).toBeInTheDocument();
  });
});
