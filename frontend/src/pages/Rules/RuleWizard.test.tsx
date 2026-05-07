import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { RuleWizard } from './RuleWizard';

vi.mock('../../api/client', () => ({
  api: {
    get: vi.fn().mockResolvedValue({
      categories: [
        {
          category: 'account_compromise',
          display_name: 'Account Compromise',
          rules: [
            {
              name: 'Impossible Travel Login',
              slug: 'impossible-travel-login',
              description: 'Detect suspicious travel patterns.',
              category: 'account_compromise',
              default_severity: 'high',
              default_confidence: 'high',
              logic_type: 'statistical',
              logic_config: { action_filters: ['auth.login'] },
            },
          ],
        },
      ],
      total_rules: 1,
    }),
  },
}));

vi.mock('../../api/rules', () => ({
  createRule: vi.fn().mockResolvedValue({ id: 1 }),
}));

describe('RuleWizard', () => {
  it('renders stepper and start from scratch option', async () => {
    renderWithProviders(<RuleWizard onClose={() => {}} onCreated={() => {}} />);

    expect(await screen.findByLabelText(/rule wizard progress/i)).toBeInTheDocument();
    expect(screen.getByText(/start from scratch/i)).toBeInTheDocument();
  });

  it('navigates forward and backward through steps', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RuleWizard onClose={() => {}} onCreated={() => {}} />);

    await user.click(await screen.findByRole('button', { name: /next/i }));

    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
    expect(screen.getByText(/2\. basic info/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /back/i }));

    expect(screen.getByText(/start from scratch/i)).toBeInTheDocument();
  });
});
