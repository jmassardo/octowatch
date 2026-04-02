import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Autocomplete } from './Autocomplete';

// JSDOM does not implement scrollIntoView
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const SUGGESTIONS = [
  'git.clone',
  'git.push',
  'pull_request.create',
  'repo.create',
  'repo.destroy',
  'team.add_member',
];

function renderAutocomplete(overrides: Partial<Parameters<typeof Autocomplete>[0]> = {}) {
  const defaultProps = {
    value: '',
    onChange: vi.fn(),
    suggestions: SUGGESTIONS,
    placeholder: 'Type here...',
    onCommit: vi.fn(),
    ariaLabel: 'test autocomplete',
    ...overrides,
  };

  const result = render(<Autocomplete {...defaultProps} />);
  return { ...result, props: defaultProps };
}

/** Focus the combobox input and trigger React's onFocus handler. */
function focusInput() {
  fireEvent.focus(screen.getByRole('combobox'));
}

describe('Autocomplete', () => {
  it('renders an input with the given placeholder', () => {
    renderAutocomplete();
    expect(screen.getByPlaceholderText('Type here...')).toBeInTheDocument();
  });

  it('renders an input with the given value', () => {
    renderAutocomplete({ value: 'git' });
    expect(screen.getByDisplayValue('git')).toBeInTheDocument();
  });

  it('calls onChange when user types', async () => {
    const user = userEvent.setup();
    const { props } = renderAutocomplete();

    await user.type(screen.getByRole('combobox'), 'g');
    expect(props.onChange).toHaveBeenCalled();
  });

  it('shows filtered suggestions when input has value', () => {
    renderAutocomplete({ value: 'git' });
    focusInput();

    expect(screen.getByText((_, el) => el?.textContent === 'git.clone')).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === 'git.push')).toBeInTheDocument();
    // repo.create should not appear for 'git' query
    expect(screen.queryByRole('option', { name: 'repo.create' })).not.toBeInTheDocument();
  });

  it('does not show dropdown when value is empty', () => {
    renderAutocomplete({ value: '' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows substring matches (not just prefix)', () => {
    renderAutocomplete({ value: 'create' });
    focusInput();

    expect(
      screen.getByText((_, el) => el?.textContent === 'pull_request.create'),
    ).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === 'repo.create')).toBeInTheDocument();
  });

  it('selects a suggestion on click', async () => {
    const user = userEvent.setup();
    const { props } = renderAutocomplete({ value: 'git' });

    focusInput();

    const option = screen.getByRole('option', { name: /git\.clone/ });
    await user.click(option);

    expect(props.onChange).toHaveBeenCalledWith('git.clone');
    expect(props.onCommit).toHaveBeenCalledWith('git.clone');
  });

  it('navigates suggestions with arrow keys', async () => {
    const user = userEvent.setup();
    const { props } = renderAutocomplete({ value: 'git' });

    // Use click to focus, which syncs userEvent's focus tracking
    await user.click(screen.getByRole('combobox'));

    await user.keyboard('{ArrowDown}');
    // First option should be active
    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{ArrowDown}');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    expect(options[0]).toHaveAttribute('aria-selected', 'false');

    // Enter to select
    await user.keyboard('{Enter}');
    expect(props.onCommit).toHaveBeenCalledWith('git.push');
  });

  it('wraps around when navigating past the last option', async () => {
    const user = userEvent.setup();
    renderAutocomplete({ value: 'git' });

    await user.click(screen.getByRole('combobox'));

    // git.clone, git.push = 2 options
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');
    await user.keyboard('{ArrowDown}');

    const options = screen.getAllByRole('option');
    // Should wrap to first
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('closes dropdown on Escape', async () => {
    const user = userEvent.setup();
    renderAutocomplete({ value: 'git' });

    await user.click(screen.getByRole('combobox'));

    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('calls onCommit with current value on Enter when no suggestion highlighted', async () => {
    const user = userEvent.setup();
    const { props } = renderAutocomplete({ value: 'custom.action' });

    await user.click(screen.getByRole('combobox'));

    // No matching suggestions for 'custom.action', so Enter commits current value
    await user.keyboard('{Enter}');
    expect(props.onCommit).toHaveBeenCalledWith('custom.action');
  });

  it('selects on Tab when a suggestion is active', async () => {
    const user = userEvent.setup();
    const { props } = renderAutocomplete({ value: 'git' });

    await user.click(screen.getByRole('combobox'));

    await user.keyboard('{ArrowDown}');
    await user.keyboard('{Tab}');

    expect(props.onCommit).toHaveBeenCalledWith('git.clone');
  });

  it('limits visible suggestions to 8', () => {
    const manySuggestions = Array.from({ length: 20 }, (_, i) => `action.${i}`);
    renderAutocomplete({ value: 'action', suggestions: manySuggestions });

    focusInput();

    const options = screen.getAllByRole('option');
    expect(options.length).toBeLessThanOrEqual(8);
  });

  it('highlights matching text in bold', () => {
    renderAutocomplete({ value: 'clone' });
    focusInput();

    // The HighlightedText component renders the matching part in a span
    const option = screen.getByRole('option');
    const highlight = option.querySelector('span');
    expect(highlight).not.toBeNull();
    expect(highlight?.textContent).toBe('clone');
  });

  it('applies custom className to the input', () => {
    renderAutocomplete({ className: 'my-custom-class' });
    const input = screen.getByRole('combobox');
    expect(input.className).toContain('my-custom-class');
  });

  it('has correct ARIA attributes', () => {
    renderAutocomplete({ value: 'git', ariaLabel: 'Search actions' });
    focusInput();

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('aria-label', 'Search actions');
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
    expect(input).toHaveAttribute('aria-expanded', 'true');
  });

  it('ArrowUp wraps to last option from top', async () => {
    const user = userEvent.setup();
    renderAutocomplete({ value: 'git' });

    await user.click(screen.getByRole('combobox'));

    await user.keyboard('{ArrowUp}');
    const options = screen.getAllByRole('option');
    // Should wrap to last option
    expect(options[options.length - 1]).toHaveAttribute('aria-selected', 'true');
  });
});
