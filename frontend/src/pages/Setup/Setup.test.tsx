import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SetupPage } from './index';

const mockSetupLogin = vi.fn().mockResolvedValue(undefined);
const mockSetupGitHubOAuth = vi.fn().mockResolvedValue(undefined);
const mockSetupGitHubApp = vi.fn().mockResolvedValue(undefined);
const mockSetupTLS = vi.fn().mockResolvedValue(undefined);
const mockCompleteSetup = vi.fn().mockResolvedValue(undefined);

vi.mock('../../api/setup', () => ({
  setupLogin: (...args: unknown[]) => mockSetupLogin(...args),
  setupGitHubOAuth: (...args: unknown[]) => mockSetupGitHubOAuth(...args),
  setupGitHubApp: (...args: unknown[]) => mockSetupGitHubApp(...args),
  setupTLS: (...args: unknown[]) => mockSetupTLS(...args),
  completeSetup: (...args: unknown[]) => mockCompleteSetup(...args),
  getSetupStatus: vi.fn().mockResolvedValue({ setup_required: true }),
  getSetupCurrentConfig: vi.fn().mockResolvedValue({}),
  listSettings: vi.fn().mockResolvedValue([]),
  updateSetting: vi.fn().mockResolvedValue({}),
  deleteSetting: vi.fn().mockResolvedValue(undefined),
  getSettingsAuditTrail: vi.fn().mockResolvedValue([]),
}));

const mockTriggerSync = vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'pending' });
const mockGetSyncStatus = vi.fn().mockResolvedValue(null);

vi.mock('../../api/sync', () => ({
  triggerSync: (...args: unknown[]) => mockTriggerSync(...args),
  getSyncStatus: (...args: unknown[]) => mockGetSyncStatus(...args),
}));

describe('SetupPage', () => {
  beforeEach(() => {
    mockSetupLogin.mockClear();
    mockSetupGitHubOAuth.mockClear();
    mockSetupGitHubApp.mockClear();
    mockSetupTLS.mockClear();
    mockCompleteSetup.mockClear();
    mockTriggerSync.mockClear();
    mockGetSyncStatus.mockClear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Helper: authenticate and advance past step 1. */
  async function authenticateStep(user: ReturnType<typeof userEvent.setup>) {
    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'token123');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));
    await waitFor(() => {
      expect(screen.getByText(/step 2 of 6/i)).toBeInTheDocument();
    });
  }

  /** Helper: navigate from step 2 to step N by skipping. */
  async function skipToStep(user: ReturnType<typeof userEvent.setup>, targetStep: number) {
    for (let step = 2; step < targetStep; step++) {
      await user.click(screen.getByRole('button', { name: /skip/i }));
      await waitFor(() => {
        expect(screen.getByText(new RegExp(`step ${step + 1} of 6`, 'i'))).toBeInTheDocument();
      });
    }
  }

  /* ---------------------------------------------------------------- */
  /*  Initial render                                                    */
  /* ---------------------------------------------------------------- */

  it('renders the setup wizard title', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByRole('heading', { level: 1, name: /octowatch setup/i })).toBeInTheDocument();
    expect(screen.getByText(/configure your instance to get started/i)).toBeInTheDocument();
  });

  it('shows step 1 of 6 initially', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByText(/step 1 of 6: authenticate/i)).toBeInTheDocument();
  });

  it('renders the token input field on step 1', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByLabelText(/setup token/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/enter your setup token/i)).toBeInTheDocument();
  });

  it('shows a hint about finding the setup token', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByText(/find your setup token in the container logs/i)).toBeInTheDocument();
  });

  it('renders the stepper with 6 steps', () => {
    const { container } = renderWithProviders(<SetupPage />);

    // Each step is a div inside the stepper container
    const stepper = container.querySelector('[class*="stepper"]');
    expect(stepper).toBeInTheDocument();
    expect(stepper!.children).toHaveLength(6);
  });

  /* ---------------------------------------------------------------- */
  /*  Token authentication                                              */
  /* ---------------------------------------------------------------- */

  it('authenticate button is disabled when token is empty', () => {
    renderWithProviders(<SetupPage />);

    const btn = screen.getByRole('button', { name: /authenticate/i });
    expect(btn).toBeDisabled();
  });

  it('calls setupLogin and advances to step 2 on success', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'my-secret-token');

    const btn = screen.getByRole('button', { name: /authenticate/i });
    await user.click(btn);

    await waitFor(() => {
      expect(mockSetupLogin).toHaveBeenCalledWith({ token: 'my-secret-token' });
    });

    await waitFor(() => {
      expect(screen.getByText(/step 2 of 6: github oauth/i)).toBeInTheDocument();
    });
  });

  it('shows error message on invalid token', async () => {
    mockSetupLogin.mockRejectedValueOnce(new Error('Invalid token'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'wrong-token');

    const btn = screen.getByRole('button', { name: /authenticate/i });
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/invalid setup token/i)).toBeInTheDocument();
    });

    // Should still be on step 1
    expect(screen.getByText(/step 1 of 6: authenticate/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Step navigation                                                   */
  /* ---------------------------------------------------------------- */

  it('navigates through all steps via skip buttons', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Step 1: authenticate
    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'token123');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    // Step 2: GitHub OAuth - skip
    await waitFor(() => {
      expect(screen.getByText(/step 2 of 6: github oauth/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 3: GitHub App - skip
    await waitFor(() => {
      expect(screen.getByText(/step 3 of 6: github app/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 4: Initial Sync - skip
    await waitFor(() => {
      expect(screen.getByText(/step 4 of 6: initial sync/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 5: TLS - skip
    await waitFor(() => {
      expect(screen.getByText(/step 5 of 6: tls/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 6: Review
    await waitFor(() => {
      expect(screen.getByText(/step 6 of 6: review/i)).toBeInTheDocument();
    });

    // Review shows skipped items
    expect(screen.getByText(/authentication/i)).toBeInTheDocument();
    expect(screen.getByText('✓ Configured')).toBeInTheDocument();
  });

  it('back button returns to previous step', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Authenticate to get to step 2
    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'token123');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 2 of 6: github oauth/i)).toBeInTheDocument();
    });

    // Go back
    await user.click(screen.getByRole('button', { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 1 of 6: authenticate/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Step 2: GitHub OAuth                                              */
  /* ---------------------------------------------------------------- */

  it('shows client ID and secret fields on step 2', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Advance to step 2
    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/client id/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/client secret/i)).toBeInTheDocument();
  });

  it('skip note explains consequence of skipping OAuth', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    await waitFor(() => {
      expect(screen.getByText(/skipping oauth means users won't be able to sign in/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Step 4: Initial Sync                                              */
  /* ---------------------------------------------------------------- */

  it('shows disabled sync state when app is not configured', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Authenticate then skip OAuth and App
    await authenticateStep(user);
    await skipToStep(user, 4);

    await waitFor(() => {
      expect(screen.getByText(/step 4 of 6: initial sync/i)).toBeInTheDocument();
    });

    // Should show disabled message since app was skipped
    expect(screen.getByText(/configure a github app first to enable enterprise sync/i)).toBeInTheDocument();

    // Skip and Back buttons should be available
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();

    // Start Sync should NOT be visible
    expect(screen.queryByRole('button', { name: /start sync/i })).not.toBeInTheDocument();
  });

  it('shows sync UI when app is configured', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Authenticate
    await authenticateStep(user);

    // Skip OAuth
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => {
      expect(screen.getByText(/step 3 of 6: github app/i)).toBeInTheDocument();
    });

    // Fill in GitHub App step (configure, not skip)
    await user.type(screen.getByLabelText(/app id/i), '12345');
    await user.type(screen.getByLabelText(/private key/i), '-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----');
    await user.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 4 of 6: initial sync/i)).toBeInTheDocument();
    });

    // Should show the full sync UI
    expect(screen.getByText(/initial enterprise sync/i)).toBeInTheDocument();
    expect(screen.getByText(/sync your github enterprise metadata/i)).toBeInTheDocument();
    expect(screen.getByText(/audit log events can be imported separately/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start sync/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument();
  });

  it('calls triggerSync when Start Sync is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to sync step with app configured
    await authenticateStep(user);
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3 of 6/i));
    await user.type(screen.getByLabelText(/app id/i), '12345');
    await user.type(screen.getByLabelText(/private key/i), '-----BEGIN RSA PRIVATE KEY-----\ntest');
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/step 4 of 6/i));

    await user.click(screen.getByRole('button', { name: /start sync/i }));

    await waitFor(() => {
      expect(mockTriggerSync).toHaveBeenCalledWith('full');
    });
  });

  it('shows Retry button when sync fails to start', async () => {
    mockTriggerSync.mockRejectedValueOnce(new Error('Network error'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to sync step with app configured
    await authenticateStep(user);
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3 of 6/i));
    await user.type(screen.getByLabelText(/app id/i), '12345');
    await user.type(screen.getByLabelText(/private key/i), '-----BEGIN RSA PRIVATE KEY-----\ntest');
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/step 4 of 6/i));

    await user.click(screen.getByRole('button', { name: /start sync/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to start sync/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('shows success state when sync completes via polling', async () => {
    mockGetSyncStatus.mockResolvedValue({
      id: 'run-1',
      status: 'completed',
      trigger_type: 'manual',
      triggered_by: null,
      scope: 'full',
      started_at: '2024-01-01T00:00:00Z',
      completed_at: '2024-01-01T00:01:00Z',
      error_message: null,
      entity_counts: { orgs: 3, repos: 42, members: 15 },
      cursors: [],
    });

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to sync step with app configured
    await authenticateStep(user);
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3 of 6/i));
    await user.type(screen.getByLabelText(/app id/i), '12345');
    await user.type(screen.getByLabelText(/private key/i), '-----BEGIN RSA PRIVATE KEY-----\ntest');
    await user.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => screen.getByText(/step 4 of 6/i));

    await user.click(screen.getByRole('button', { name: /start sync/i }));

    // Advance timer to trigger polling
    await vi.advanceTimersByTimeAsync(5000);

    await waitFor(() => {
      expect(screen.getByText(/✓ sync complete!/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
  });

  it('skip on sync step advances to TLS without marking sync complete', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to sync step with app skipped (disabled state)
    await authenticateStep(user);
    await skipToStep(user, 4);

    await waitFor(() => {
      expect(screen.getByText(/step 4 of 6: initial sync/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /skip/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 5 of 6: tls/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Step 5: TLS                                                       */
  /* ---------------------------------------------------------------- */

  it('hides PEM fields when self-signed is checked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to TLS step (now step 5)
    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));
    await waitFor(() => screen.getByText(/step 2/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 4/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 5 of 6: tls/i)).toBeInTheDocument();
    });

    // Certificate PEM should be visible
    expect(screen.getByLabelText(/certificate \(pem\)/i)).toBeInTheDocument();

    // Check self-signed
    await user.click(screen.getByLabelText(/generate self-signed certificate/i));

    // Certificate PEM should be hidden
    expect(screen.queryByLabelText(/certificate \(pem\)/i)).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Step 6: Review & Complete                                         */
  /* ---------------------------------------------------------------- */

  it('shows Initial Sync in review items', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to review step
    await authenticateStep(user);
    await skipToStep(user, 6);

    await waitFor(() => {
      expect(screen.getByText(/step 6 of 6: review/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Initial Sync')).toBeInTheDocument();
  });

  it('shows completion banner after completing setup', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<SetupPage />);

    // Navigate to review step
    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));
    await waitFor(() => screen.getByText(/step 2/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 4/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 5/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 6 of 6: review/i)).toBeInTheDocument();
    });

    // Complete setup
    await user.click(screen.getByRole('button', { name: /complete setup/i }));

    await waitFor(() => {
      expect(mockCompleteSetup).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText(/setup complete!/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/redirecting to login page/i)).toBeInTheDocument();
  });
});
