import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { RuleLibrary } from './RuleLibrary';

vi.mock('../../api/client', () => ({
  api: {
    get: vi.fn((path: string) => {
      if (path === '/rules/library') {
        return Promise.resolve({
          categories: [
            {
              category: 'account_compromise',
              display_name: 'Account Compromise',
              rules: [
                {
                  name: 'Impossible Travel Login',
                  slug: 'impossible-travel-login',
                  description: 'Detects logins from distant locations.',
                  category: 'account_compromise',
                  default_severity: 'high',
                  default_confidence: 'high',
                  logic_type: 'statistical',
                  logic_config: {},
                },
                {
                  name: 'Brute Force Login',
                  slug: 'brute-force-login',
                  description: 'Detects multiple failed login attempts.',
                  category: 'account_compromise',
                  default_severity: 'high',
                  default_confidence: 'high',
                  logic_type: 'threshold',
                  logic_config: {},
                },
              ],
            },
            {
              category: 'privilege_escalation',
              display_name: 'Privilege Escalation',
              rules: [
                {
                  name: 'Admin Role Grant',
                  slug: 'admin-role-grant',
                  description: 'Detects admin role grants.',
                  category: 'privilege_escalation',
                  default_severity: 'high',
                  default_confidence: 'high',
                  logic_type: 'pattern',
                  logic_config: {},
                },
              ],
            },
          ],
          total_rules: 3,
        });
      }
      if (path.includes('/customize')) {
        return Promise.resolve({
          rule: {
            name: 'Impossible Travel Login',
            slug: 'impossible-travel-login',
            description: 'Detects logins from distant locations.',
            category: 'account_compromise',
            default_severity: 'high',
            default_confidence: 'high',
            logic_type: 'statistical',
            logic_config: {},
            enabled: false,
            status: 'draft',
          },
        });
      }
      return Promise.resolve({});
    }),
    post: vi.fn(() =>
      Promise.resolve({
        id: 99,
        name: 'Impossible Travel Login',
        slug: 'impossible-travel-login',
        category: 'account_compromise',
        default_severity: 'high',
        default_confidence: 'high',
        logic_type: 'statistical',
        logic_config: {},
        enabled: true,
        status: 'active',
        version: 1,
        created_by: 'testuser',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      }),
    ),
  },
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number;
    body: unknown;
    constructor(status: number, body: unknown, message: string) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

describe('RuleLibrary', () => {
  it('renders title and subtitle', async () => {
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    expect(await screen.findByText('Rule Library')).toBeInTheDocument();
    expect(screen.getByText(/3 pre-built detection rules/)).toBeInTheDocument();
  });

  it('shows category headers', async () => {
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    expect(await screen.findByText('Account Compromise')).toBeInTheDocument();
    expect(screen.getByText('Privilege Escalation')).toBeInTheDocument();
  });

  it('shows category rule counts', async () => {
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    expect(await screen.findByText('2 rules')).toBeInTheDocument();
    expect(screen.getByText('1 rules')).toBeInTheDocument();
  });

  it('expands category on click to show rules', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    const categoryHeader = await screen.findByText('Account Compromise');
    await user.click(categoryHeader);

    expect(screen.getByText('Impossible Travel Login')).toBeInTheDocument();
    expect(screen.getByText('Brute Force Login')).toBeInTheDocument();
  });

  it('shows Enable and Customize buttons for rules', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    const categoryHeader = await screen.findByText('Account Compromise');
    await user.click(categoryHeader);

    const enableButtons = screen.getAllByRole('button', { name: /enable/i });
    expect(enableButtons.length).toBe(2);

    const customizeButtons = screen.getAllByRole('button', { name: /customize/i });
    expect(customizeButtons.length).toBe(2);
  });

  it('calls onClose when back button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    const backButton = await screen.findByRole('button', { name: /back to rules/i });
    await user.click(backButton);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows severity badges', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    const categoryHeader = await screen.findByText('Account Compromise');
    await user.click(categoryHeader);

    // Should show severity labels
    const highLabels = screen.getAllByText('high');
    expect(highLabels.length).toBeGreaterThanOrEqual(2);
  });

  it('shows rule descriptions', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<RuleLibrary onClose={onClose} />);

    const categoryHeader = await screen.findByText('Account Compromise');
    await user.click(categoryHeader);

    expect(screen.getByText(/detects logins from distant locations/i)).toBeInTheDocument();
  });
});
