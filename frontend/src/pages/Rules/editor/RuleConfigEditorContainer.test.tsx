import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/utils';
import { RuleConfigEditorContainer } from './RuleConfigEditorContainer';

const mockValidateRuleConfig = vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] });

vi.mock('../../../api/rules', () => ({
  validateRuleConfig: (...args: unknown[]) => mockValidateRuleConfig(...args),
}));

// Mock LogicConfigEditor since it's built by another agent and tested separately
vi.mock('./LogicConfigEditor', () => ({
  LogicConfigEditor: ({
    logicType,
    errors,
  }: {
    logicType: string;
    config: Record<string, unknown>;
    onChange: (config: Record<string, unknown>) => void;
    errors?: string[];
  }) => (
    <div data-testid="visual-editor">
      <span>Visual editor for {logicType}</span>
      {errors && errors.length > 0 && (
        <div data-testid="visual-errors">{errors.join(', ')}</div>
      )}
    </div>
  ),
}));

describe('RuleConfigEditorContainer', () => {
  const defaultConfig = { threshold: 10, action_filters: [] };

  beforeEach(() => {
    mockValidateRuleConfig.mockClear();
    mockValidateRuleConfig.mockResolvedValue({ valid: true, errors: [], warnings: [] });
  });

  /* ---------------------------------------------------------------- */
  /*  Mode toggle                                                      */
  /* ---------------------------------------------------------------- */

  it('renders Visual and JSON mode tabs', () => {
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    expect(screen.getByTestId('mode-visual')).toBeInTheDocument();
    expect(screen.getByTestId('mode-json')).toBeInTheDocument();
  });

  it('defaults to Visual mode', () => {
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    expect(screen.getByTestId('visual-editor')).toBeInTheDocument();
    expect(screen.queryByTestId('json-textarea')).not.toBeInTheDocument();
  });

  it('switches to JSON mode when JSON tab is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    await user.click(screen.getByTestId('mode-json'));

    expect(screen.getByTestId('json-textarea')).toBeInTheDocument();
    expect(screen.queryByTestId('visual-editor')).not.toBeInTheDocument();
  });

  it('switches back to Visual mode from JSON when JSON is valid', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    // Go to JSON mode
    await user.click(screen.getByTestId('mode-json'));
    expect(screen.getByTestId('json-textarea')).toBeInTheDocument();

    // Go back to Visual
    await user.click(screen.getByTestId('mode-visual'));
    expect(screen.getByTestId('visual-editor')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Switch safety                                                    */
  /* ---------------------------------------------------------------- */

  it('prevents switching to Visual when JSON is invalid', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    // Go to JSON mode
    await user.click(screen.getByTestId('mode-json'));

    // Type invalid JSON
    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, 'broken');

    // Try to switch to Visual
    await user.click(screen.getByTestId('mode-visual'));

    // Should show warning and stay in JSON mode
    expect(screen.getByTestId('switch-warning')).toBeInTheDocument();
    expect(screen.getByText('Fix JSON errors before switching to Visual mode')).toBeInTheDocument();
    expect(screen.getByTestId('json-textarea')).toBeInTheDocument();
  });

  it('clears switch warning when JSON becomes valid again', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    // Go to JSON mode
    await user.click(screen.getByTestId('mode-json'));

    // Type invalid JSON
    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, 'broken');

    // Try to switch — warning appears
    await user.click(screen.getByTestId('mode-visual'));
    expect(screen.getByTestId('switch-warning')).toBeInTheDocument();

    // Fix the JSON
    await user.clear(textarea);
    await user.type(textarea, '{{"ok": true}');

    // Warning should be cleared
    expect(screen.queryByTestId('switch-warning')).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Bidirectional sync                                               */
  /* ---------------------------------------------------------------- */

  it('JSON editor receives the current config', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    await user.click(screen.getByTestId('mode-json'));

    const textarea = screen.getByTestId('json-textarea');
    expect(textarea).toHaveValue(JSON.stringify(defaultConfig, null, 2));
  });

  it('calls onChange when JSON is edited with valid content', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByTestId('mode-json'));

    const textarea = screen.getByTestId('json-textarea');
    await user.clear(textarea);
    await user.type(textarea, '{{"threshold": 20}');

    expect(onChange).toHaveBeenCalledWith({ threshold: 20 });
  });

  /* ---------------------------------------------------------------- */
  /*  Visual editor                                                    */
  /* ---------------------------------------------------------------- */

  it('shows correct logic type in visual editor', () => {
    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="pattern"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText('Visual editor for pattern')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Validation                                                       */
  /* ---------------------------------------------------------------- */

  it('calls validateRuleConfig on mount (debounced)', async () => {
    vi.useFakeTimers();

    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    // Advance past debounce
    vi.advanceTimersByTime(600);

    expect(mockValidateRuleConfig).toHaveBeenCalledWith('threshold', defaultConfig);

    vi.useRealTimers();
  });

  it('passes validation errors to the active editor', async () => {
    vi.useFakeTimers();
    mockValidateRuleConfig.mockResolvedValue({
      valid: false,
      errors: ['Threshold too low'],
      warnings: [],
    });

    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    vi.advanceTimersByTime(600);

    // Wait for the async validation to resolve
    await vi.waitFor(() => {
      expect(screen.getByTestId('visual-errors')).toHaveTextContent('Threshold too low');
    });

    vi.useRealTimers();
  });

  it('handles validation endpoint failure gracefully', async () => {
    vi.useFakeTimers();
    mockValidateRuleConfig.mockRejectedValue(new Error('Network error'));

    renderWithProviders(
      <RuleConfigEditorContainer
        logicType="threshold"
        config={defaultConfig}
        onChange={() => {}}
      />,
    );

    vi.advanceTimersByTime(600);

    // Should not crash, should render normally
    await vi.waitFor(() => {
      expect(screen.getByTestId('visual-editor')).toBeInTheDocument();
    });

    vi.useRealTimers();
  });
});
