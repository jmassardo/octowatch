import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { OnboardingWizard, type OnboardingResult } from './OnboardingWizard';
import { isOnboardingComplete } from './onboardingStorage';

describe('OnboardingWizard', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the welcome step and persona options', () => {
    renderWithProviders(
      <OnboardingWizard availableOrganizations={['acme', 'globex']} onComplete={vi.fn()} />,
    );

    expect(screen.getByText(/welcome to your dashboard/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /security analyst/i })).toBeInTheDocument();
    expect(screen.getByText(/step 1 of 4/i)).toBeInTheDocument();
  });

  it('uses persona defaults for widget selection', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <OnboardingWizard availableOrganizations={['acme', 'globex']} onComplete={vi.fn()} />,
    );

    await user.click(screen.getByRole('button', { name: /devops engineer/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));

    expect(screen.getByLabelText(/sync health/i)).toBeChecked();
    expect(screen.getByLabelText(/event volume/i)).toBeChecked();
    expect(screen.getByLabelText(/copilot usage/i)).toBeChecked();
  });

  it('completes onboarding and stores completion state', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn<(result: OnboardingResult) => void>();

    renderWithProviders(
      <OnboardingWizard availableOrganizations={['acme', 'globex']} onComplete={onComplete} />,
    );

    await user.click(screen.getByRole('button', { name: /engineering lead/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByLabelText(/globex/i));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByLabelText(/slack nudges/i));
    await user.click(screen.getByRole('button', { name: /launch dashboard/i }));

    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        persona: 'engineering-lead',
        organizations: ['acme'],
        notifications: expect.objectContaining({ slack: true }),
      }),
    );
    expect(localStorage.getItem('octowatch-onboarding-complete')).toBe('true');
    expect(isOnboardingComplete()).toBe(true);
  });
});
