import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WidgetCatalog } from './WidgetCatalog';
import { renderWithProviders } from '../../test/utils';
import type { CatalogWidget } from '../../api/dashboardConfig';

const mockWidgets: CatalogWidget[] = [
  {
    id: 'unified-security',
    title: 'Unified Security',
    description: 'Cross-signal security posture',
    category: 'security',
    default_w: 12,
    default_h: 4,
  },
  {
    id: 'sync-health',
    title: 'Sync Health',
    description: 'Current sync status',
    category: 'operations',
    default_w: 4,
    default_h: 3,
  },
  {
    id: 'copilot-usage',
    title: 'Copilot Usage',
    description: 'Adoption snapshot',
    category: 'copilot',
    default_w: 4,
    default_h: 3,
  },
];

describe('WidgetCatalog', () => {
  const onClose = vi.fn();
  const onAdd = vi.fn();
  const onRemove = vi.fn();

  beforeEach(() => {
    onClose.mockClear();
    onAdd.mockClear();
    onRemove.mockClear();
  });

  it('renders widgets grouped by category when open', () => {
    renderWithProviders(
      <WidgetCatalog
        open={true}
        onClose={onClose}
        widgets={mockWidgets}
        activeWidgetIds={new Set()}
        onAdd={onAdd}
        onRemove={onRemove}
      />,
    );

    expect(screen.getByText('Unified Security')).toBeInTheDocument();
    expect(screen.getByText('Sync Health')).toBeInTheDocument();
    expect(screen.getByText('Copilot Usage')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Copilot')).toBeInTheDocument();
  });

  it('filters widgets by search term', () => {
    renderWithProviders(
      <WidgetCatalog
        open={true}
        onClose={onClose}
        widgets={mockWidgets}
        activeWidgetIds={new Set()}
        onAdd={onAdd}
        onRemove={onRemove}
      />,
    );

    const searchbox = screen.getByRole('searchbox', { name: /search widgets/i });
    fireEvent.change(searchbox, { target: { value: 'copilot' } });

    expect(screen.getByText('Copilot Usage')).toBeInTheDocument();
    expect(screen.queryByText('Unified Security')).not.toBeInTheDocument();
    expect(screen.queryByText('Sync Health')).not.toBeInTheDocument();
  });

  it('calls onAdd when Add button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WidgetCatalog
        open={true}
        onClose={onClose}
        widgets={mockWidgets}
        activeWidgetIds={new Set()}
        onAdd={onAdd}
        onRemove={onRemove}
      />,
    );

    const addButtons = screen.getAllByRole('button', { name: /^Add$/i });
    await user.click(addButtons[0]!);

    expect(onAdd).toHaveBeenCalledWith('unified-security');
  });

  it('shows Remove button for active widgets', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WidgetCatalog
        open={true}
        onClose={onClose}
        widgets={mockWidgets}
        activeWidgetIds={new Set(['unified-security'])}
        onAdd={onAdd}
        onRemove={onRemove}
      />,
    );

    const removeBtn = screen.getByRole('button', { name: /^Remove$/i });
    await user.click(removeBtn);

    expect(onRemove).toHaveBeenCalledWith('unified-security');
  });

  it('shows empty state when no widgets match search', async () => {
    renderWithProviders(
      <WidgetCatalog
        open={true}
        onClose={onClose}
        widgets={mockWidgets}
        activeWidgetIds={new Set()}
        onAdd={onAdd}
        onRemove={onRemove}
      />,
    );

    const searchbox = screen.getByRole('searchbox', { name: /search widgets/i });
    fireEvent.change(searchbox, { target: { value: 'zzzznonexistent' } });

    expect(screen.getByText('No widgets match your search.')).toBeInTheDocument();
  });
});
