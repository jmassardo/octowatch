import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import {
  GuidedTour,
} from '../../components/GuidedTour/GuidedTour';
import { isTourCompleted, resetTour } from '../../components/GuidedTour/tourStorage';

// Mock document.querySelector to return fake elements with getBoundingClientRect
const mockElement = {
  getBoundingClientRect: () => ({
    top: 100,
    left: 50,
    right: 250,
    bottom: 140,
    width: 200,
    height: 40,
    x: 50,
    y: 100,
    toJSON: () => {},
  }),
};

const originalQuerySelector = document.querySelector.bind(document);

beforeEach(() => {
  localStorage.clear();
  document.querySelector = vi.fn((selector: string) => {
    // Return mock element for tour target selectors
    if (selector.startsWith('[href=')) {
      return mockElement as unknown as Element;
    }
    return originalQuerySelector(selector);
  }) as typeof document.querySelector;
});

describe('GuidedTour', () => {
  it('renders the first step with title and description', () => {
    renderWithProviders(<GuidedTour />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText(/your security command center/i)).toBeInTheDocument();
    expect(screen.getByText('1 of 6')).toBeInTheDocument();
  });

  it('advances to next step when Next is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /next/i }));

    expect(screen.getByText('Threat Detections')).toBeInTheDocument();
    expect(screen.getByText('2 of 6')).toBeInTheDocument();
  });

  it('goes back to previous step when Back is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour />);

    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.getByText('Threat Detections')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /back/i }));
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('does not show Back button on first step', () => {
    renderWithProviders(<GuidedTour />);

    expect(screen.queryByRole('button', { name: /back/i })).not.toBeInTheDocument();
  });

  it('shows Get Started button on last step', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour />);

    // Click through all steps to reach the last one
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getByRole('button', { name: /next/i }));
    }

    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument();
  });

  it('calls onComplete when tour is finished', async () => {
    const onComplete = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour onComplete={onComplete} />);

    // Click through all steps
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getByRole('button', { name: /next/i }));
    }
    await user.click(screen.getByRole('button', { name: /get started/i }));

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('calls onComplete when close button is clicked', async () => {
    const onComplete = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour onComplete={onComplete} />);

    await user.click(screen.getByRole('button', { name: /close tour/i }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('saves completion to localStorage', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour />);

    await user.click(screen.getByRole('button', { name: /close tour/i }));
    expect(localStorage.getItem('octowatch_tour_completed')).toBe('true');
  });

  it('renders step progress dots', () => {
    renderWithProviders(<GuidedTour />);

    // Should have 6 dots
    const dots = document.querySelectorAll('[class*="dot"]');
    expect(dots.length).toBe(6);
  });

  it('has an accessible dialog role', () => {
    renderWithProviders(<GuidedTour />);

    expect(screen.getByRole('dialog', { name: /guided tour/i })).toBeInTheDocument();
  });

  it('renders the third step about Rules correctly', async () => {
    const user = userEvent.setup();
    renderWithProviders(<GuidedTour />);

    await user.click(screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));

    expect(screen.getByText('Detection Rules')).toBeInTheDocument();
    expect(screen.getByText(/enable detection rules/i)).toBeInTheDocument();
    expect(screen.getByText('3 of 6')).toBeInTheDocument();
  });
});

describe('isTourCompleted', () => {
  it('returns false when tour has not been completed', () => {
    expect(isTourCompleted()).toBe(false);
  });

  it('returns true when tour has been completed', () => {
    localStorage.setItem('octowatch_tour_completed', 'true');
    expect(isTourCompleted()).toBe(true);
  });
});

describe('resetTour', () => {
  it('removes the tour completion flag from localStorage', () => {
    localStorage.setItem('octowatch_tour_completed', 'true');
    resetTour();
    expect(localStorage.getItem('octowatch_tour_completed')).toBeNull();
  });
});
