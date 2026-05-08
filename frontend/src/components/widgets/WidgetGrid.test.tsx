import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WidgetGrid } from './WidgetGrid';
import { renderWithProviders } from '../../test/utils';
import type { WidgetDefinition, WidgetLayoutItem } from './WidgetRegistry';

const definitions: WidgetDefinition[] = [
  {
    id: 'alpha',
    title: 'Alpha Widget',
    description: 'Primary signal',
    defaultSize: 'sm',
    category: 'security',
    component: () => <div>Alpha content</div>,
  },
  {
    id: 'beta',
    title: 'Beta Widget',
    description: 'Secondary signal',
    defaultSize: 'md',
    category: 'operations',
    component: () => <div>Beta content</div>,
  },
  {
    id: 'gamma',
    title: 'Gamma Widget',
    description: 'Tertiary signal',
    defaultSize: 'lg',
    category: 'activity',
    component: () => <div>Gamma content</div>,
  },
];

function renderGrid(layout: WidgetLayoutItem[], onChange = vi.fn()) {
  renderWithProviders(<WidgetGrid layout={layout} onChange={onChange} definitions={definitions} />);
  return onChange;
}

describe('WidgetGrid', () => {
  it('renders configured widgets', () => {
    renderGrid([
      { id: 'alpha', size: 'sm' },
      { id: 'beta', size: 'md' },
    ]);

    expect(screen.getByText('Alpha Widget')).toBeInTheDocument();
    expect(screen.getByText('Beta Widget')).toBeInTheDocument();
    expect(screen.getByText('Alpha content')).toBeInTheDocument();
  });

  it('removes a widget from the layout', async () => {
    const user = userEvent.setup();
    const onChange = renderGrid([{ id: 'alpha', size: 'sm' }]);

    await user.click(screen.getByRole('button', { name: /remove alpha widget/i }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it('cycles widget sizes from the resize grip', async () => {
    const user = userEvent.setup();
    const onChange = renderGrid([{ id: 'alpha', size: 'sm' }]);

    await user.click(screen.getByRole('button', { name: /resize alpha widget to medium/i }));

    expect(onChange).toHaveBeenCalledWith([{ id: 'alpha', size: 'md' }]);
  });

  it('adds widgets from the customize modal', async () => {
    const user = userEvent.setup();
    const onChange = renderGrid([{ id: 'alpha', size: 'sm' }]);

    await user.click(screen.getByRole('button', { name: /customize/i }));
    const picker = screen.getByRole('dialog', { name: /customize dashboard widgets/i });
    await user.click(within(picker).getAllByRole('button', { name: /^Add$/i })[0]!);

    expect(onChange).toHaveBeenCalledWith([
      { id: 'alpha', size: 'sm' },
      { id: 'beta', size: 'md' },
    ]);
  });

  it('renders drag handles for each widget card', () => {
    renderGrid([
      { id: 'alpha', size: 'sm' },
      { id: 'beta', size: 'md' },
    ]);

    expect(screen.getByRole('button', { name: /drag alpha widget/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /drag beta widget/i })).toBeInTheDocument();
  });
});
