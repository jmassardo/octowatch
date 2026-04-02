import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { MetricCard } from './MetricCard';

describe('MetricCard', () => {
  /* ---------------------------------------------------------------- */
  /*  Basic rendering                                                   */
  /* ---------------------------------------------------------------- */

  it('renders value and label', () => {
    renderWithProviders(<MetricCard value="42" label="Total items" />);

    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Total items')).toBeInTheDocument();
  });

  it('renders delta text when provided', () => {
    renderWithProviders(
      <MetricCard value="10" label="Count" delta="+5 from yesterday" deltaDir="up" />,
    );

    expect(screen.getByText('+5 from yesterday')).toBeInTheDocument();
  });

  it('does not render delta when not provided', () => {
    const { container } = renderWithProviders(<MetricCard value="7" label="Items" />);

    expect(container.querySelector('.delta')).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Non-clickable state                                               */
  /* ---------------------------------------------------------------- */

  it('does not have button role when not clickable', () => {
    renderWithProviders(<MetricCard value="0" label="Static card" />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('does not render arrow when not clickable', () => {
    const { container } = renderWithProviders(<MetricCard value="0" label="Static card" />);

    expect(container.querySelector('.arrow')).not.toBeInTheDocument();
  });

  it('does not apply clickable class when not interactive', () => {
    const { container } = renderWithProviders(<MetricCard value="0" label="Static" />);

    expect(container.querySelector('.clickable')).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Clickable with onClick                                            */
  /* ---------------------------------------------------------------- */

  it('renders as button role when onClick is provided', () => {
    renderWithProviders(<MetricCard value="5" label="Clickable" onClick={() => {}} />);

    expect(screen.getByRole('button', { name: 'Clickable' })).toBeInTheDocument();
  });

  it('renders arrow indicator when clickable', () => {
    const { container } = renderWithProviders(
      <MetricCard value="5" label="Clickable" onClick={() => {}} />,
    );

    expect(container.querySelector('.arrow')).toBeInTheDocument();
    expect(container.querySelector('.arrow')?.textContent).toBe('→');
  });

  it('applies clickable class when onClick is provided', () => {
    const { container } = renderWithProviders(
      <MetricCard value="5" label="Clickable" onClick={() => {}} />,
    );

    expect(container.querySelector('.clickable')).toBeInTheDocument();
  });

  it('calls onClick handler when clicked', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    renderWithProviders(<MetricCard value="5" label="Click me" onClick={handleClick} />);

    await user.click(screen.getByRole('button', { name: 'Click me' }));
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('calls onClick on Enter key press', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    renderWithProviders(<MetricCard value="3" label="Keyboard card" onClick={handleClick} />);

    const card = screen.getByRole('button', { name: 'Keyboard card' });
    card.focus();
    await user.keyboard('{Enter}');
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('calls onClick on Space key press', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    renderWithProviders(<MetricCard value="3" label="Space card" onClick={handleClick} />);

    const card = screen.getByRole('button', { name: 'Space card' });
    card.focus();
    await user.keyboard(' ');
    expect(handleClick).toHaveBeenCalledOnce();
  });

  it('has tabIndex 0 when clickable', () => {
    renderWithProviders(<MetricCard value="1" label="Focusable" onClick={() => {}} />);

    const card = screen.getByRole('button', { name: 'Focusable' });
    expect(card).toHaveAttribute('tabindex', '0');
  });

  /* ---------------------------------------------------------------- */
  /*  Clickable with `to` (router navigation)                          */
  /* ---------------------------------------------------------------- */

  it('renders as clickable when `to` is provided', () => {
    renderWithProviders(<MetricCard value="8" label="Navigate card" to="/events" />);

    expect(screen.getByRole('button', { name: 'Navigate card' })).toBeInTheDocument();
  });

  it('renders arrow indicator when `to` is provided', () => {
    const { container } = renderWithProviders(
      <MetricCard value="8" label="Nav card" to="/events" />,
    );

    expect(container.querySelector('.arrow')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Accent variant                                                    */
  /* ---------------------------------------------------------------- */

  it('applies accented class when accent prop is true', () => {
    const { container } = renderWithProviders(<MetricCard value="99" label="Alert" accent />);

    expect(container.querySelector('.accented')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Arrow is hidden from screen readers                               */
  /* ---------------------------------------------------------------- */

  it('hides arrow from assistive technology', () => {
    const { container } = renderWithProviders(
      <MetricCard value="1" label="Card" onClick={() => {}} />,
    );

    const arrow = container.querySelector('.arrow');
    expect(arrow).toHaveAttribute('aria-hidden', 'true');
  });
});
