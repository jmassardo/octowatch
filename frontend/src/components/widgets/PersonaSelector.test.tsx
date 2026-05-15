import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PersonaSelector } from './PersonaSelector';
import { renderWithProviders } from '../../test/utils';

describe('PersonaSelector', () => {
  const onSelect = vi.fn();
  const onSkip = vi.fn();

  beforeEach(() => {
    onSelect.mockClear();
    onSkip.mockClear();
  });

  it('renders all four personas when open', () => {
    renderWithProviders(<PersonaSelector open={true} onSelect={onSelect} onSkip={onSkip} />);

    expect(screen.getByText('Security Analyst')).toBeInTheDocument();
    expect(screen.getByText('Engineering Manager')).toBeInTheDocument();
    expect(screen.getByText('Platform Engineer')).toBeInTheDocument();
    expect(screen.getByText('Executive')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderWithProviders(<PersonaSelector open={false} onSelect={onSelect} onSkip={onSkip} />);

    expect(screen.queryByText('Security Analyst')).not.toBeInTheDocument();
  });

  it('selects a persona and calls onSelect when Apply is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PersonaSelector open={true} onSelect={onSelect} onSkip={onSkip} />);

    await user.click(screen.getByText('Platform Engineer'));
    await user.click(screen.getByRole('button', { name: /apply layout/i }));

    expect(onSelect).toHaveBeenCalledWith('platform-engineer');
  });

  it('calls onSkip when skip button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PersonaSelector open={true} onSelect={onSelect} onSkip={onSkip} />);

    await user.click(screen.getByRole('button', { name: /skip/i }));

    expect(onSkip).toHaveBeenCalled();
  });

  it('disables Apply button until a persona is selected', () => {
    renderWithProviders(<PersonaSelector open={true} onSelect={onSelect} onSkip={onSkip} />);

    const applyBtn = screen.getByRole('button', { name: /apply layout/i });
    expect(applyBtn).toBeDisabled();
  });
});
