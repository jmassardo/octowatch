import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { AutomationPage } from './index';

const mockFetchTargets = vi.fn();
const mockFetchDeliveries = vi.fn();

vi.mock('../../api/automation', () => ({
  fetchTargets: (...args: unknown[]) => mockFetchTargets(...args),
  fetchDeliveries: (...args: unknown[]) => mockFetchDeliveries(...args),
  createTarget: vi.fn(),
  updateTarget: vi.fn(),
  deleteTarget: vi.fn(),
  testTarget: vi.fn(),
  retryDelivery: vi.fn(),
}));

describe('AutomationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchTargets.mockResolvedValue({ targets: [] });
    mockFetchDeliveries.mockResolvedValue({ deliveries: [] });
  });

  it('renders page header', async () => {
    renderWithProviders(<AutomationPage />);
    expect(screen.getByText('Automation')).toBeInTheDocument();
    expect(screen.getByText('Configure automated responses to detections.')).toBeInTheDocument();
  });

  it('shows targets tab by default', async () => {
    renderWithProviders(<AutomationPage />);
    const targetsTab = screen.getByRole('button', { name: 'Targets' });
    expect(targetsTab.className).toContain('tabActive');
  });

  it('displays targets from API', async () => {
    mockFetchTargets.mockResolvedValue({
      targets: [
        {
          id: 1,
          name: 'Slack Webhook',
          target_type: 'webhook',
          webhook_url: 'https://hooks.slack.com/test',
          dispatch_repo: null,
          dispatch_event_type: null,
          rule_ids: [],
          rule_categories: [],
          severity_filter: [],
          org_filter: [],
          is_catch_all: false,
          rate_limit_per_minute: 60,
          max_retries: 3,
          enabled: true,
          created_by: 'admin',
          created_at: '2026-01-15T10:00:00Z',
          updated_at: '2026-01-15T10:00:00Z',
        },
        {
          id: 2,
          name: 'CI Dispatch',
          target_type: 'dispatch',
          webhook_url: null,
          dispatch_repo: 'org/repo',
          dispatch_event_type: 'security-alert',
          rule_ids: [1, 2],
          rule_categories: ['critical'],
          severity_filter: ['high'],
          org_filter: [],
          is_catch_all: false,
          rate_limit_per_minute: 10,
          max_retries: 5,
          enabled: false,
          created_by: 'admin',
          created_at: '2026-02-01T12:00:00Z',
          updated_at: '2026-02-01T12:00:00Z',
        },
      ],
    });

    renderWithProviders(<AutomationPage />);

    await waitFor(() => {
      expect(screen.getByText('Slack Webhook')).toBeInTheDocument();
    });
    expect(screen.getByText('CI Dispatch')).toBeInTheDocument();
  });

  it('shows delivery history tab when clicked', async () => {
    const user = userEvent.setup();
    mockFetchDeliveries.mockResolvedValue({
      deliveries: [
        {
          id: 10,
          target_id: 1,
          detection_id: 42,
          status: 'delivered',
          attempts: 1,
          last_attempt_at: '2026-01-15T11:00:00Z',
          next_retry_at: null,
          response_code: 200,
          error_message: null,
          payload_hash: 'abc123',
          is_dry_run: false,
          created_at: '2026-01-15T10:59:00Z',
          target_name: 'Slack Webhook',
          target_type: 'webhook',
        },
      ],
    });

    renderWithProviders(<AutomationPage />);

    const deliveriesTab = screen.getByRole('button', { name: 'Deliveries' });
    await user.click(deliveriesTab);

    await waitFor(() => {
      expect(screen.getByText('Slack Webhook')).toBeInTheDocument();
    });
    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText('delivered')).toBeInTheDocument();
  });

  it('handles empty state', async () => {
    renderWithProviders(<AutomationPage />);

    await waitFor(() => {
      expect(screen.getByText(/No automation targets configured/)).toBeInTheDocument();
    });
  });
});
