import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/utils';
import { LogicConfigEditor } from './LogicConfigEditor';
import type { LogicConfig } from './types';

function renderEditor(
  overrides: {
    logicType?: 'pattern' | 'threshold' | 'sequence' | 'statistical';
    config?: LogicConfig;
    onChange?: (config: LogicConfig) => void;
    errors?: string[];
  } = {},
) {
  const props = {
    logicType: overrides.logicType ?? 'pattern',
    config: overrides.config ?? {},
    onChange: overrides.onChange ?? vi.fn(),
    errors: overrides.errors,
  };
  return renderWithProviders(<LogicConfigEditor {...props} />);
}

describe('LogicConfigEditor', () => {
  describe('common sections', () => {
    it('renders all common section headers', () => {
      renderEditor();

      expect(screen.getByText('Action Filters')).toBeInTheDocument();
      expect(screen.getByText('Field Conditions')).toBeInTheDocument();
      expect(screen.getByText('Confidence')).toBeInTheDocument();
    });

    it('renders the confidence slider with default value 0.50', () => {
      renderEditor();

      const slider = screen.getByRole('slider', { name: /confidence score/i });
      expect(slider).toBeInTheDocument();
      expect(slider).toHaveValue('0.5');
      expect(screen.getByText('0.50')).toBeInTheDocument();
    });

    it('adjusts confidence value on slider change', async () => {
      const onChange = vi.fn();
      renderEditor({ onChange, config: { confidence: 0.5 } });

      const slider = screen.getByRole('slider', { name: /confidence score/i });
      // fireEvent works better for range inputs
      await userEvent.click(slider);
      // Directly update via fireEvent since userEvent doesn't handle range well
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set;
      nativeInputValueSetter?.call(slider, '0.8');
      slider.dispatchEvent(new Event('input', { bubbles: true }));
      slider.dispatchEvent(new Event('change', { bubbles: true }));

      expect(onChange).toHaveBeenCalled();
      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
      expect(lastCall?.confidence).toBe(0.8);
    });

    it('displays errors when provided', () => {
      renderEditor({
        errors: ['Missing action filters', 'Threshold must be > 0'],
      });

      expect(screen.getByText('Missing action filters')).toBeInTheDocument();
      expect(screen.getByText('Threshold must be > 0')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('does not display error list when errors is empty', () => {
      renderEditor({ errors: [] });

      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('pattern type', () => {
    it('does not show threshold, sequence, or statistical sections', () => {
      renderEditor({ logicType: 'pattern' });

      expect(screen.queryByText('Threshold')).not.toBeInTheDocument();
      expect(screen.queryByText('Sequence Steps')).not.toBeInTheDocument();
      expect(screen.queryByText('Statistical Analysis')).not.toBeInTheDocument();
    });
  });

  describe('threshold type', () => {
    it('renders threshold-specific fields', () => {
      renderEditor({ logicType: 'threshold' });

      expect(screen.getByText('Threshold')).toBeInTheDocument();
      expect(screen.getByLabelText('Alert when count exceeds')).toBeInTheDocument();
      expect(screen.getByLabelText('Within time window (minutes)')).toBeInTheDocument();
      expect(screen.getByLabelText('Group events by')).toBeInTheDocument();
      expect(screen.getByLabelText('Count distinct values of')).toBeInTheDocument();
    });

    it('renders default threshold values for empty config', () => {
      renderEditor({ logicType: 'threshold' });

      expect(screen.getByLabelText('Alert when count exceeds')).toHaveValue(10);
      expect(
        screen.getByLabelText('Within time window (minutes)'),
      ).toHaveValue(60);
    });

    it('updates threshold on number input change', () => {
      const onChange = vi.fn();
      renderEditor({
        logicType: 'threshold',
        config: {
          threshold: 10,
          time_window_minutes: 60,
          aggregation_key: 'actor',
          confidence: 0.5,
          action_filters: [],
          field_conditions: [],
        },
        onChange,
      });

      const thresholdInput = screen.getByLabelText('Alert when count exceeds');
      // Use fireEvent.change for controlled components with mocked onChange
      thresholdInput.focus();
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set;
      nativeSetter?.call(thresholdInput, '25');
      thresholdInput.dispatchEvent(new Event('change', { bubbles: true }));

      expect(onChange).toHaveBeenCalled();
      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
      expect(lastCall?.threshold).toBe(25);
    });

    it('does not show sequence or statistical sections', () => {
      renderEditor({ logicType: 'threshold' });

      expect(screen.queryByText('Sequence Steps')).not.toBeInTheDocument();
      expect(screen.queryByText('Statistical Analysis')).not.toBeInTheDocument();
    });
  });

  describe('sequence type', () => {
    it('renders sequence-specific fields', () => {
      renderEditor({ logicType: 'sequence' });

      expect(screen.getByText('Sequence Steps')).toBeInTheDocument();
      expect(screen.getByRole('list', { name: /sequence steps/i })).toBeInTheDocument();
    });

    it('initializes with 2 default steps for empty config', () => {
      renderEditor({ logicType: 'sequence' });

      const listItems = screen.getAllByRole('listitem');
      expect(listItems).toHaveLength(2);
    });

    it('renders step badges with numbers', () => {
      renderEditor({ logicType: 'sequence' });

      expect(screen.getByLabelText('Step 1')).toHaveTextContent('1');
      expect(screen.getByLabelText('Step 2')).toHaveTextContent('2');
    });

    it('does not show threshold or statistical sections', () => {
      renderEditor({ logicType: 'sequence' });

      expect(screen.queryByText('Threshold')).not.toBeInTheDocument();
      expect(screen.queryByText('Statistical Analysis')).not.toBeInTheDocument();
    });
  });

  describe('statistical type', () => {
    it('renders statistical-specific fields', () => {
      renderEditor({ logicType: 'statistical' });

      expect(screen.getByText('Statistical Analysis')).toBeInTheDocument();
      expect(screen.getByLabelText('Engine')).toBeInTheDocument();
      expect(screen.getByLabelText('Distance threshold (km)')).toBeInTheDocument();
      expect(screen.getByLabelText('Speed threshold (km/h)')).toBeInTheDocument();
      expect(screen.getByLabelText('Suppress proxy IPs')).toBeInTheDocument();
    });

    it('renders default statistical values for empty config', () => {
      renderEditor({ logicType: 'statistical' });

      expect(screen.getByLabelText('Distance threshold (km)')).toHaveValue(500);
      expect(screen.getByLabelText('Speed threshold (km/h)')).toHaveValue(900);
      expect(screen.getByLabelText('Suppress proxy IPs')).toBeChecked();
    });

    it('toggles suppress proxy IPs checkbox', async () => {
      const onChange = vi.fn();
      renderEditor({
        logicType: 'statistical',
        config: {
          confidence: 0.5,
          action_filters: [],
          field_conditions: [],
          time_window_minutes: 60,
          x_config: {
            engine: 'impossible_travel',
            distance_threshold_km: 500,
            speed_threshold_kmh: 900,
            suppress_proxy_ips: true,
          },
        },
        onChange,
      });

      const checkbox = screen.getByLabelText('Suppress proxy IPs');
      await userEvent.click(checkbox);

      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
      expect(lastCall?.x_config?.suppress_proxy_ips).toBe(false);
    });

    it('does not show threshold or sequence sections', () => {
      renderEditor({ logicType: 'statistical' });

      expect(screen.queryByText('Threshold')).not.toBeInTheDocument();
      expect(screen.queryByText('Sequence Steps')).not.toBeInTheDocument();
    });
  });

  describe('pre-populated config', () => {
    it('renders existing action filters as chips', () => {
      renderEditor({
        config: {
          action_filters: ['git.clone', 'repo.create'],
          confidence: 0.7,
        },
      });

      expect(screen.getByText('git.clone')).toBeInTheDocument();
      expect(screen.getByText('repo.create')).toBeInTheDocument();
    });

    it('renders existing field conditions', () => {
      renderEditor({
        config: {
          field_conditions: [
            { field: 'data.scope', operator: 'eq', value: 'read' },
          ],
          confidence: 0.5,
        },
      });

      const fieldInput = screen.getByDisplayValue('data.scope');
      expect(fieldInput).toBeInTheDocument();

      const valueInput = screen.getByDisplayValue('read');
      expect(valueInput).toBeInTheDocument();
    });

    it('renders confidence from config', () => {
      renderEditor({ config: { confidence: 0.85 } });

      expect(screen.getByText('0.85')).toBeInTheDocument();
    });
  });
});

describe('ActionFilters', () => {
  it('adds action on Enter key', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: { action_filters: [], confidence: 0.5 },
      onChange,
    });

    const input = screen.getByLabelText('Add action filter');
    await userEvent.type(input, 'git.push{Enter}');

    const calls = onChange.mock.calls;
    const matchingCall = calls.find(
      (call: LogicConfig[]) => call[0]?.action_filters?.includes('git.push'),
    );
    expect(matchingCall).toBeTruthy();
  });

  it('adds action on comma', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: { action_filters: [], confidence: 0.5 },
      onChange,
    });

    const input = screen.getByLabelText('Add action filter');
    await userEvent.type(input, 'git.push,');

    const calls = onChange.mock.calls;
    const matchingCall = calls.find(
      (call: LogicConfig[]) => call[0]?.action_filters?.includes('git.push'),
    );
    expect(matchingCall).toBeTruthy();
  });

  it('does not add duplicate actions', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: { action_filters: ['git.clone'], confidence: 0.5 },
      onChange,
    });

    const input = screen.getByLabelText('Add action filter');
    await userEvent.type(input, 'git.clone{Enter}');

    // Should not create a call with duplicate
    const calls = onChange.mock.calls;
    const duplicateCall = calls.find(
      (call: LogicConfig[]) => {
        const filters = call[0]?.action_filters;
        return filters && filters.filter((f: string) => f === 'git.clone').length > 1;
      },
    );
    expect(duplicateCall).toBeUndefined();
  });

  it('removes action when × button is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: { action_filters: ['git.clone', 'repo.create'], confidence: 0.5 },
      onChange,
    });

    const removeBtn = screen.getByLabelText('Remove action git.clone');
    await userEvent.click(removeBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.action_filters).toEqual(['repo.create']);
  });
});

describe('FieldConditions', () => {
  it('adds a condition row when "Add condition" is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: { field_conditions: [], confidence: 0.5 },
      onChange,
    });

    const addBtn = screen.getByText('+ Add condition');
    await userEvent.click(addBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.field_conditions).toHaveLength(1);
    expect(lastCall?.field_conditions?.[0]).toEqual({
      field: '',
      operator: 'eq',
      value: '',
    });
  });

  it('removes a condition row when × is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: {
        field_conditions: [
          { field: 'a', operator: 'eq', value: '1' },
          { field: 'b', operator: 'ne', value: '2' },
        ],
        confidence: 0.5,
      },
      onChange,
    });

    const removeBtn = screen.getByLabelText('Remove condition 1');
    await userEvent.click(removeBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.field_conditions).toHaveLength(1);
    expect(lastCall?.field_conditions?.[0]?.field).toBe('b');
  });

  it('hides value input for exists operator', async () => {
    renderEditor({
      config: {
        field_conditions: [{ field: 'test', operator: 'exists', value: undefined }],
        confidence: 0.5,
      },
    });

    // Value input should not exist
    expect(screen.queryByLabelText('Condition 1 value')).not.toBeInTheDocument();
  });

  it('hides value input for not_exists operator', () => {
    renderEditor({
      config: {
        field_conditions: [{ field: 'test', operator: 'not_exists', value: undefined }],
        confidence: 0.5,
      },
    });

    expect(screen.queryByLabelText('Condition 1 value')).not.toBeInTheDocument();
  });

  it('shows placeholder for in operator', () => {
    renderEditor({
      config: {
        field_conditions: [{ field: 'test', operator: 'in', value: '' }],
        confidence: 0.5,
      },
    });

    const valueInput = screen.getByLabelText('Condition 1 value');
    expect(valueInput).toHaveAttribute('placeholder', 'comma-separated values');
  });

  it('updates field value on typing', () => {
    const onChange = vi.fn();
    renderEditor({
      config: {
        field_conditions: [{ field: '', operator: 'eq', value: '' }],
        confidence: 0.5,
      },
      onChange,
    });

    const fieldInput = screen.getByLabelText('Condition 1 field');
    // Use native setter for controlled component with mocked onChange
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    nativeSetter?.call(fieldInput, 'actor');
    fieldInput.dispatchEvent(new Event('change', { bubbles: true }));

    expect(onChange).toHaveBeenCalled();
    const calls = onChange.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall?.field_conditions?.[0]?.field).toBe('actor');
  });

  it('updates operator on selection change', async () => {
    const onChange = vi.fn();
    renderEditor({
      config: {
        field_conditions: [{ field: 'test', operator: 'eq', value: '' }],
        confidence: 0.5,
      },
      onChange,
    });

    const operatorSelect = screen.getByLabelText('Condition 1 operator');
    await userEvent.selectOptions(operatorSelect, 'contains');

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.field_conditions?.[0]?.operator).toBe('contains');
  });
});

describe('SequenceSteps', () => {
  it('adds a step when "Add step" is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'git.clone', min_count: 1 },
          { action: 'git.push', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
      onChange,
    });

    const addBtn = screen.getByText('+ Add step');
    await userEvent.click(addBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.sequence_steps).toHaveLength(3);
  });

  it('removes a step when × is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'git.clone', min_count: 1 },
          { action: 'git.push', min_count: 1 },
          { action: 'repo.delete', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
      onChange,
    });

    const removeBtn = screen.getByLabelText('Remove step 2');
    await userEvent.click(removeBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.sequence_steps).toHaveLength(2);
    expect(lastCall?.sequence_steps?.[1]?.action).toBe('repo.delete');
  });

  it('moves step up when ↑ is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'first', min_count: 1 },
          { action: 'second', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
      onChange,
    });

    const moveUpBtn = screen.getByLabelText('Move step 2 up');
    await userEvent.click(moveUpBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.sequence_steps?.[0]?.action).toBe('second');
    expect(lastCall?.sequence_steps?.[1]?.action).toBe('first');
  });

  it('moves step down when ↓ is clicked', async () => {
    const onChange = vi.fn();
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'first', min_count: 1 },
          { action: 'second', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
      onChange,
    });

    const moveDownBtn = screen.getByLabelText('Move step 1 down');
    await userEvent.click(moveDownBtn);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
    expect(lastCall?.sequence_steps?.[0]?.action).toBe('second');
    expect(lastCall?.sequence_steps?.[1]?.action).toBe('first');
  });

  it('disables move up on first step', () => {
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'first', min_count: 1 },
          { action: 'second', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
    });

    const moveUpBtn = screen.getByLabelText('Move step 1 up');
    expect(moveUpBtn).toBeDisabled();
  });

  it('disables move down on last step', () => {
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: 'first', min_count: 1 },
          { action: 'second', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
    });

    const moveDownBtn = screen.getByLabelText('Move step 2 down');
    expect(moveDownBtn).toBeDisabled();
  });

  it('updates step action on typing', () => {
    const onChange = vi.fn();
    renderEditor({
      logicType: 'sequence',
      config: {
        sequence_steps: [
          { action: '', min_count: 1 },
          { action: '', min_count: 1 },
        ],
        aggregation_key: 'actor',
        time_window_minutes: 60,
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
      onChange,
    });

    const actionInput = screen.getByLabelText('Step 1 action');
    // Use native setter for controlled component with mocked onChange
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set;
    nativeSetter?.call(actionInput, 'git.clone');
    actionInput.dispatchEvent(new Event('change', { bubbles: true }));

    expect(onChange).toHaveBeenCalled();
    const calls = onChange.mock.calls;
    const lastCall = calls[calls.length - 1]?.[0];
    expect(lastCall?.sequence_steps?.[0]?.action).toBe('git.clone');
  });
});

describe('accessibility', () => {
  it('has aria-label on editor form', () => {
    renderEditor();

    expect(
      screen.getByRole('form', { name: /logic configuration editor/i }),
    ).toBeInTheDocument();
  });

  it('has aria-label on action filters group', () => {
    renderEditor();

    expect(
      screen.getByRole('group', { name: /action filters/i }),
    ).toBeInTheDocument();
  });

  it('has aria-label on field conditions group', () => {
    renderEditor();

    expect(
      screen.getByRole('group', { name: /field conditions/i }),
    ).toBeInTheDocument();
  });

  it('sequence steps have role list and listitem', () => {
    renderEditor({ logicType: 'sequence' });

    const list = screen.getByRole('list', { name: /sequence steps/i });
    expect(list).toBeInTheDocument();

    const items = within(list).getAllByRole('listitem');
    expect(items.length).toBeGreaterThanOrEqual(2);
  });

  it('all remove buttons have descriptive aria-labels', () => {
    renderEditor({
      config: {
        action_filters: ['git.clone'],
        field_conditions: [{ field: 'test', operator: 'eq', value: 'v' }],
        confidence: 0.5,
      },
    });

    expect(
      screen.getByLabelText('Remove action git.clone'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Remove condition 1')).toBeInTheDocument();
  });

  it('all inputs are keyboard accessible', () => {
    renderEditor({
      logicType: 'threshold',
      config: {
        threshold: 10,
        time_window_minutes: 60,
        aggregation_key: 'actor',
        confidence: 0.5,
        action_filters: [],
        field_conditions: [],
      },
    });

    const allInputs = screen.getAllByRole('spinbutton');
    for (const input of allInputs) {
      expect(input.tabIndex).not.toBe(-1);
    }

    const allSelects = screen.getAllByRole('combobox');
    for (const select of allSelects) {
      expect(select.tabIndex).not.toBe(-1);
    }
  });
});
