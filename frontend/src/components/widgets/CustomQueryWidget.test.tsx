import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { CustomQueryWidget } from './CustomQueryWidget';
import { CustomQueryWidgetInstance } from './CustomQueryWidgetInstance';
import { CreateCustomWidgetDialog } from './CreateCustomWidgetDialog';
import {
  CUSTOM_WIDGETS_STORAGE_KEY,
  loadCustomWidgetConfigs,
  createCustomWidgetConfig,
  deleteCustomWidgetConfig,
  getCustomWidgetConfig,
  generateCustomWidgetId,
} from './customWidgetConfigStorage';

// Mock the query API
vi.mock('../../api/query', () => ({
  runQuery: vi.fn(),
  listSavedQueries: vi.fn().mockResolvedValue([
    {
      id: 1,
      name: 'Event Counts',
      sql_text: 'SELECT action, COUNT(*) FROM events GROUP BY action',
      description: null,
      owner_login: 'user',
      is_shared: false,
      shared_with: null,
      tags: null,
      schedule_cron: null,
      schedule_enabled: false,
      last_run_at: null,
      created_at: '2024-01-01',
      updated_at: null,
    },
    {
      id: 2,
      name: 'Top Repos',
      sql_text: 'SELECT repo, COUNT(*) FROM events GROUP BY repo',
      description: null,
      owner_login: 'user',
      is_shared: false,
      shared_with: null,
      tags: null,
      schedule_cron: null,
      schedule_enabled: false,
      last_run_at: null,
      created_at: '2024-01-01',
      updated_at: null,
    },
  ]),
}));

describe('customWidgetConfigStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('generates unique widget IDs', () => {
    const id1 = generateCustomWidgetId();
    const id2 = generateCustomWidgetId();
    expect(id1).not.toBe(id2);
    expect(id1).toMatch(/^custom-query-/);
  });

  it('loads empty array when no configs stored', () => {
    expect(loadCustomWidgetConfigs()).toEqual([]);
  });

  it('creates and persists a widget config', () => {
    const config = createCustomWidgetConfig({
      title: 'Test Widget',
      description: 'A test',
      inlineSql: 'SELECT 1',
      visualizationType: 'bar',
      refreshIntervalSeconds: 30,
    });

    expect(config.title).toBe('Test Widget');
    expect(config.visualizationType).toBe('bar');
    expect(config.id).toMatch(/^custom-query-/);

    const loaded = loadCustomWidgetConfigs();
    expect(loaded).toHaveLength(1);
    expect(loaded[0]!.title).toBe('Test Widget');
  });

  it('gets a single config by ID', () => {
    const config = createCustomWidgetConfig({
      title: 'Lookup Widget',
      visualizationType: 'line',
      inlineSql: 'SELECT date, count FROM daily',
    });

    const found = getCustomWidgetConfig(config.id);
    expect(found).not.toBeNull();
    expect(found!.title).toBe('Lookup Widget');
  });

  it('returns null for nonexistent ID', () => {
    expect(getCustomWidgetConfig('nonexistent')).toBeNull();
  });

  it('deletes a widget config', () => {
    const config = createCustomWidgetConfig({
      title: 'To Delete',
      visualizationType: 'table',
      inlineSql: 'SELECT *',
    });

    expect(deleteCustomWidgetConfig(config.id)).toBe(true);
    expect(loadCustomWidgetConfigs()).toHaveLength(0);
  });

  it('returns false when deleting nonexistent config', () => {
    expect(deleteCustomWidgetConfig('nonexistent')).toBe(false);
  });

  it('handles invalid JSON gracefully', () => {
    localStorage.setItem(CUSTOM_WIDGETS_STORAGE_KEY, 'not json');
    expect(loadCustomWidgetConfigs()).toEqual([]);
  });

  it('filters out invalid configs', () => {
    localStorage.setItem(
      CUSTOM_WIDGETS_STORAGE_KEY,
      JSON.stringify([
        {
          id: 'valid',
          title: 'Valid',
          visualizationType: 'bar',
          description: '',
          inlineSql: '',
          savedQueryId: null,
          refreshIntervalSeconds: 0,
          createdAt: '2024-01-01',
        },
        { id: 123, title: 'Bad ID' }, // invalid: id not string
        { title: 'No ID', visualizationType: 'bar' }, // invalid: no id
        { id: 'bad-viz', title: 'Bad Viz', visualizationType: 'unknown' }, // invalid viz type
      ]),
    );
    const configs = loadCustomWidgetConfigs();
    expect(configs).toHaveLength(1);
    expect(configs[0]!.id).toBe('valid');
  });
});

describe('CustomQueryWidget', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('shows creation prompt when no custom widgets exist', () => {
    renderWithProviders(<CustomQueryWidget />);
    expect(screen.getByText(/create custom widgets from your saved queries/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create custom widget/i })).toBeInTheDocument();
  });

  it('shows widget count when custom widgets exist', () => {
    createCustomWidgetConfig({
      title: 'Widget 1',
      visualizationType: 'bar',
      inlineSql: 'SELECT 1',
    });
    createCustomWidgetConfig({
      title: 'Widget 2',
      visualizationType: 'line',
      inlineSql: 'SELECT 2',
    });

    renderWithProviders(<CustomQueryWidget />);
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText(/custom widgets/)).toBeInTheDocument();
  });

  it('dispatches event when create button clicked', async () => {
    const user = userEvent.setup();
    const handler = vi.fn();
    window.addEventListener('octowatch:open-custom-widget-dialog', handler);

    renderWithProviders(<CustomQueryWidget />);
    await user.click(screen.getByRole('button', { name: /create custom widget/i }));

    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener('octowatch:open-custom-widget-dialog', handler);
  });
});

describe('CustomQueryWidgetInstance', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('shows error when config not found', () => {
    renderWithProviders(<CustomQueryWidgetInstance widgetId="nonexistent-id" />);
    expect(screen.getByText(/widget configuration not found/i)).toBeInTheDocument();
  });

  it('shows no query message when SQL is empty', () => {
    const config = createCustomWidgetConfig({
      title: 'Empty Widget',
      visualizationType: 'bar',
      inlineSql: '',
    });

    renderWithProviders(<CustomQueryWidgetInstance widgetId={config.id} />);
    expect(screen.getByText(/no query configured/i)).toBeInTheDocument();
  });
});

describe('CreateCustomWidgetDialog', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders when open', () => {
    renderWithProviders(
      <CreateCustomWidgetDialog open={true} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    expect(screen.getByRole('dialog', { name: /create custom widget/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/widget title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/visualization type/i)).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    renderWithProviders(
      <CreateCustomWidgetDialog open={false} onClose={vi.fn()} onCreated={vi.fn()} />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('validates that title is required', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();

    renderWithProviders(
      <CreateCustomWidgetDialog open={true} onClose={vi.fn()} onCreated={onCreated} />,
    );

    await user.click(screen.getByRole('button', { name: /create widget/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/title is required/i);
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('validates that inline SQL is required when inline source selected', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();

    renderWithProviders(
      <CreateCustomWidgetDialog open={true} onClose={vi.fn()} onCreated={onCreated} />,
    );

    // Use fireEvent for inputs to avoid async re-render race conditions
    const titleInput = screen.getByRole('textbox', { name: /widget title/i });
    fireEvent.change(titleInput, { target: { value: 'Test Title' } });

    // Switch to inline mode
    await user.click(screen.getByLabelText(/write sql inline/i));

    // Submit without SQL
    await user.click(screen.getByRole('button', { name: /create widget/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/please enter a sql query/i);
    expect(onCreated).not.toHaveBeenCalled();
  });

  it('creates widget with inline SQL successfully', async () => {
    const user = userEvent.setup();
    const onCreated = vi.fn();
    const onClose = vi.fn();

    renderWithProviders(
      <CreateCustomWidgetDialog open={true} onClose={onClose} onCreated={onCreated} />,
    );

    // Use fireEvent for reliable input value setting
    const titleInput = screen.getByRole('textbox', { name: /widget title/i });
    fireEvent.change(titleInput, { target: { value: 'MyWidget' } });

    // Switch to inline mode
    await user.click(screen.getByLabelText(/write sql inline/i));

    // Type SQL in textarea
    const textarea = screen.getByRole('textbox', { name: /sql query/i });
    fireEvent.change(textarea, { target: { value: 'SELECT 1 as val' } });

    // Select pie chart
    await user.selectOptions(screen.getByLabelText(/visualization type/i), 'pie');

    await user.click(screen.getByRole('button', { name: /create widget/i }));

    expect(onCreated).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);

    // Verify config was persisted
    const configs = loadCustomWidgetConfigs();
    expect(configs).toHaveLength(1);
    expect(configs[0]!.title).toBe('MyWidget');
    expect(configs[0]!.visualizationType).toBe('pie');
    expect(configs[0]!.inlineSql).toBe('SELECT 1 as val');
  });

  it('calls onClose when cancel clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    renderWithProviders(
      <CreateCustomWidgetDialog open={true} onClose={onClose} onCreated={vi.fn()} />,
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
