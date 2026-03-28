import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { JsonConfigEditor } from './JsonConfigEditor';

describe('JsonConfigEditor', () => {
  const defaultConfig = { threshold: 10, action_filters: [] };

  /* ---------------------------------------------------------------- */
  /*  Rendering                                                        */
  /* ---------------------------------------------------------------- */

  it('renders the textarea with formatted JSON', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea');
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveValue(JSON.stringify(defaultConfig, null, 2));
  });

  it('shows "Valid JSON" status for valid config', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    expect(screen.getByText('Valid JSON')).toBeInTheDocument();
  });

  it('renders line numbers in gutter', () => {
    const config = { a: 1, b: 2, c: 3 };
    render(<JsonConfigEditor config={config} onChange={() => {}} />);

    // JSON.stringify({a:1,b:2,c:3}, null, 2) produces 5 lines
    const formatted = JSON.stringify(config, null, 2);
    const expectedLineCount = formatted.split('\n').length;

    // Find the gutter element and check it contains correct line numbers
    const gutter = document.querySelector('[aria-hidden="true"]')!;
    const gutterLines = gutter.textContent!.trim().split('\n');
    expect(gutterLines).toHaveLength(expectedLineCount);
    expect(gutterLines[0]).toBe('1');
    expect(gutterLines[expectedLineCount - 1]).toBe(String(expectedLineCount));
  });

  it('renders Format and Copy buttons when not readOnly', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    expect(screen.getByRole('button', { name: /format/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument();
  });

  it('hides Format and Copy buttons in readOnly mode', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} readOnly />);

    expect(screen.queryByRole('button', { name: /format/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /copy/i })).not.toBeInTheDocument();
  });

  it('makes textarea readOnly in readOnly mode', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} readOnly />);

    const textarea = screen.getByTestId('json-textarea');
    expect(textarea).toHaveAttribute('readOnly');
  });

  /* ---------------------------------------------------------------- */
  /*  Editing behavior                                                 */
  /* ---------------------------------------------------------------- */

  it('calls onChange with parsed object when valid JSON is typed', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<JsonConfigEditor config={{}} onChange={onChange} />);

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, '{{"name": "test"}');

    expect(onChange).toHaveBeenCalledWith({ name: 'test' });
  });

  it('does NOT call onChange when JSON is invalid', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<JsonConfigEditor config={defaultConfig} onChange={onChange} />);

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    onChange.mockClear(); // Clear any calls from clear operation

    await user.type(textarea, '{{invalid');

    // onChange should not be called for invalid JSON
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows "Invalid JSON" status when JSON is invalid', async () => {
    const user = userEvent.setup();
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, 'not json');

    expect(screen.getByText('Invalid JSON')).toBeInTheDocument();
  });

  it('shows parse error detail below textarea for invalid JSON', async () => {
    const user = userEvent.setup();
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, '{{broken');

    expect(screen.getByTestId('json-parse-error')).toBeInTheDocument();
  });

  it('shows error when root value is an array', () => {
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea');
    // Use fireEvent.change to avoid user-event interpreting brackets
    fireEvent.change(textarea, { target: { value: '[1, 2, 3]' } });

    expect(screen.getByText('Root value must be a JSON object')).toBeInTheDocument();
  });

  it('calls onValidityChange with false when JSON becomes invalid', async () => {
    const user = userEvent.setup();
    const onValidityChange = vi.fn();
    render(
      <JsonConfigEditor
        config={defaultConfig}
        onChange={() => {}}
        onValidityChange={onValidityChange}
      />,
    );

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, 'bad');

    expect(onValidityChange).toHaveBeenCalledWith(false);
  });

  it('calls onValidityChange with true when JSON becomes valid', async () => {
    const user = userEvent.setup();
    const onValidityChange = vi.fn();
    render(
      <JsonConfigEditor
        config={defaultConfig}
        onChange={() => {}}
        onValidityChange={onValidityChange}
      />,
    );

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, '{{"ok": true}');

    expect(onValidityChange).toHaveBeenCalledWith(true);
  });

  /* ---------------------------------------------------------------- */
  /*  Format button                                                    */
  /* ---------------------------------------------------------------- */

  it('Format button pretty-prints the JSON', () => {
    const onChange = vi.fn();
    render(<JsonConfigEditor config={defaultConfig} onChange={onChange} />);

    const textarea = screen.getByTestId('json-textarea');
    // Use fireEvent to set compact JSON without triggering prop sync issues
    fireEvent.change(textarea, { target: { value: '{"a":1}' } });

    fireEvent.click(screen.getByRole('button', { name: /format/i }));

    expect(textarea).toHaveValue(JSON.stringify({ a: 1 }, null, 2));
  });

  it('Format button is disabled when JSON is invalid', async () => {
    const user = userEvent.setup();
    render(<JsonConfigEditor config={defaultConfig} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, 'broken');

    const formatBtn = screen.getByRole('button', { name: /format/i });
    expect(formatBtn).toBeDisabled();
  });

  /* ---------------------------------------------------------------- */
  /*  Tab key inserts spaces                                           */
  /* ---------------------------------------------------------------- */

  it('Tab key inserts 2 spaces instead of changing focus', () => {
    render(<JsonConfigEditor config={{}} onChange={() => {}} />);

    const textarea = screen.getByTestId('json-textarea') as HTMLTextAreaElement;
    // Position cursor at the beginning
    textarea.setSelectionRange(0, 0);

    fireEvent.keyDown(textarea, { key: 'Tab' });

    // The handler inserts 2 spaces at cursor position
    expect(textarea.value).toContain('  ');
  });

  /* ---------------------------------------------------------------- */
  /*  External config prop changes                                     */
  /* ---------------------------------------------------------------- */

  it('updates textarea when config prop changes', () => {
    const { rerender } = render(
      <JsonConfigEditor config={{ a: 1 }} onChange={() => {}} />,
    );

    const textarea = screen.getByTestId('json-textarea');
    expect(textarea).toHaveValue(JSON.stringify({ a: 1 }, null, 2));

    rerender(<JsonConfigEditor config={{ a: 2 }} onChange={() => {}} />);

    expect(textarea).toHaveValue(JSON.stringify({ a: 2 }, null, 2));
  });

  it('does not reset textarea when config prop has same content', () => {
    const { rerender } = render(
      <JsonConfigEditor config={{ a: 1 }} onChange={() => {}} />,
    );

    const textarea = screen.getByTestId('json-textarea');
    // User modifies text to compact form (same JSON content, different formatting)
    fireEvent.change(textarea, { target: { value: '{"a":1}' } });
    expect(textarea).toHaveValue('{"a":1}');

    // Re-render with same content but new object reference
    rerender(<JsonConfigEditor config={{ a: 1 }} onChange={() => {}} />);

    // Should NOT reset — same JSON content
    expect(textarea).toHaveValue('{"a":1}');
  });

  /* ---------------------------------------------------------------- */
  /*  Validation errors from parent                                    */
  /* ---------------------------------------------------------------- */

  it('renders validation errors passed via errors prop', () => {
    render(
      <JsonConfigEditor
        config={defaultConfig}
        onChange={() => {}}
        errors={['Threshold must be positive', 'Missing action_filters']}
      />,
    );

    expect(screen.getByText('Threshold must be positive')).toBeInTheDocument();
    expect(screen.getByText('Missing action_filters')).toBeInTheDocument();
  });

  it('does not render validation errors when errors is empty', () => {
    render(
      <JsonConfigEditor config={defaultConfig} onChange={() => {}} errors={[]} />,
    );

    expect(screen.queryByText(/must be/)).not.toBeInTheDocument();
  });
});
