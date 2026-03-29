import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SampleDataBanner } from './SampleDataBanner';

describe('SampleDataBanner', () => {
  it('renders default message when no message prop is provided', () => {
    render(<SampleDataBanner />);
    expect(
      screen.getByText(
        /Connect your GitHub audit log source to see real data/,
      ),
    ).toBeInTheDocument();
  });

  it('renders custom message when message prop is provided', () => {
    render(
      <SampleDataBanner message="This is a custom banner message." />,
    );
    expect(screen.getByText('This is a custom banner message.')).toBeInTheDocument();
  });

  it('has role="status" for accessibility', () => {
    render(<SampleDataBanner />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the info icon', () => {
    render(<SampleDataBanner />);
    expect(screen.getByText('ℹ️')).toBeInTheDocument();
  });
});
