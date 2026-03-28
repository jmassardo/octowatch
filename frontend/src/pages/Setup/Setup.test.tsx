import { describe, it, expect, vi, beforeEach } from 'vitest';
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

describe('SetupPage', () => {
  beforeEach(() => {
    mockSetupLogin.mockClear();
    mockSetupGitHubOAuth.mockClear();
    mockSetupGitHubApp.mockClear();
    mockSetupTLS.mockClear();
    mockCompleteSetup.mockClear();
  });

  /* ---------------------------------------------------------------- */
  /*  Initial render                                                    */
  /* ---------------------------------------------------------------- */

  it('renders the setup wizard title', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByRole('heading', { level: 1, name: /octowatch setup/i })).toBeInTheDocument();
    expect(screen.getByText(/configure your instance to get started/i)).toBeInTheDocument();
  });

  it('shows step 1 of 5 initially', () => {
    renderWithProviders(<SetupPage />);

    expect(screen.getByText(/step 1 of 5: authenticate/i)).toBeInTheDocument();
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

  it('renders the stepper with 5 steps', () => {
    const { container } = renderWithProviders(<SetupPage />);

    // Each step is a div inside the stepper container
    const stepper = container.querySelector('[class*="stepper"]');
    expect(stepper).toBeInTheDocument();
    expect(stepper!.children).toHaveLength(5);
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
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'my-secret-token');

    const btn = screen.getByRole('button', { name: /authenticate/i });
    await user.click(btn);

    await waitFor(() => {
      expect(mockSetupLogin).toHaveBeenCalledWith({ token: 'my-secret-token' });
    });

    await waitFor(() => {
      expect(screen.getByText(/step 2 of 5: github oauth/i)).toBeInTheDocument();
    });
  });

  it('shows error message on invalid token', async () => {
    mockSetupLogin.mockRejectedValueOnce(new Error('Invalid token'));
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'wrong-token');

    const btn = screen.getByRole('button', { name: /authenticate/i });
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByText(/invalid setup token/i)).toBeInTheDocument();
    });

    // Should still be on step 1
    expect(screen.getByText(/step 1 of 5: authenticate/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Step navigation                                                   */
  /* ---------------------------------------------------------------- */

  it('navigates through all steps via skip buttons', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    // Step 1: authenticate
    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'token123');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    // Step 2: GitHub OAuth - skip
    await waitFor(() => {
      expect(screen.getByText(/step 2 of 5: github oauth/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 3: GitHub App - skip
    await waitFor(() => {
      expect(screen.getByText(/step 3 of 5: github app/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 4: TLS - skip
    await waitFor(() => {
      expect(screen.getByText(/step 4 of 5: tls/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /skip/i }));

    // Step 5: Review
    await waitFor(() => {
      expect(screen.getByText(/step 5 of 5: review/i)).toBeInTheDocument();
    });

    // Review shows skipped items
    expect(screen.getByText(/authentication/i)).toBeInTheDocument();
    expect(screen.getByText('✓ Configured')).toBeInTheDocument();
  });

  it('back button returns to previous step', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    // Authenticate to get to step 2
    const input = screen.getByLabelText(/setup token/i);
    await user.type(input, 'token123');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 2 of 5: github oauth/i)).toBeInTheDocument();
    });

    // Go back
    await user.click(screen.getByRole('button', { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 1 of 5: authenticate/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Step 2: GitHub OAuth                                              */
  /* ---------------------------------------------------------------- */

  it('shows client ID and secret fields on step 2', async () => {
    const user = userEvent.setup();
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
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));

    await waitFor(() => {
      expect(screen.getByText(/skipping oauth means users won't be able to sign in/i)).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Step 4: TLS                                                       */
  /* ---------------------------------------------------------------- */

  it('hides PEM fields when self-signed is checked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SetupPage />);

    // Navigate to TLS step
    await user.type(screen.getByLabelText(/setup token/i), 'token');
    await user.click(screen.getByRole('button', { name: /authenticate/i }));
    await waitFor(() => screen.getByText(/step 2/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));
    await waitFor(() => screen.getByText(/step 3/i));
    await user.click(screen.getByRole('button', { name: /skip/i }));

    await waitFor(() => {
      expect(screen.getByText(/step 4 of 5: tls/i)).toBeInTheDocument();
    });

    // Certificate PEM should be visible
    expect(screen.getByLabelText(/certificate \(pem\)/i)).toBeInTheDocument();

    // Check self-signed
    await user.click(screen.getByLabelText(/generate self-signed certificate/i));

    // Certificate PEM should be hidden
    expect(screen.queryByLabelText(/certificate \(pem\)/i)).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Step 5: Review & Complete                                         */
  /* ---------------------------------------------------------------- */

  it('shows completion banner after completing setup', async () => {
    const user = userEvent.setup();
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

    await waitFor(() => {
      expect(screen.getByText(/step 5 of 5: review/i)).toBeInTheDocument();
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
