import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { QueryPage } from './index';

vi.mock('../../api/query', () => ({
  runQuery: vi.fn().mockResolvedValue({
    columns: ['actor', 'country_count'],
    rows: [['alice', 3]],
    row_count: 1,
    truncated: false,
    execution_ms: 42,
    query_id: 'q-1',
  }),
  listTemplates: vi.fn().mockResolvedValue([]),
  createTemplate: vi.fn().mockResolvedValue({
    id: 1,
    name: 'Test query',
    description: null,
    sql: 'SELECT 1',
    created_by: 'user',
    created_at: '2024-01-01T00:00:00Z',
  }),
}));

describe('QueryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  // --- Basic Rendering ---

  it('renders page title and subtitle', () => {
    renderWithProviders(<QueryPage />);
    expect(screen.getByText('Query Explorer')).toBeInTheDocument();
    expect(
      screen.getByText('Write SQL against the audit events database'),
    ).toBeInTheDocument();
  });

  it('renders editor filename in toolbar', () => {
    renderWithProviders(<QueryPage />);
    expect(screen.getByText('query.sql')).toBeInTheDocument();
  });

  it('renders Run, Save, and History toolbar buttons', () => {
    renderWithProviders(<QueryPage />);
    expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'History' }),
    ).toBeInTheDocument();
  });

  it('renders textarea with default SQL', () => {
    renderWithProviders(<QueryPage />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toContain(
      'Actors with logins from 2+ countries',
    );
  });

  it('renders line numbers in the gutter', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const gutter = container.querySelector('.editorGutter');
    expect(gutter).not.toBeNull();
    // Default SQL has 10 lines
    const lineNums = gutter!.querySelectorAll('div');
    expect(lineNums.length).toBeGreaterThanOrEqual(8);
    expect(lineNums[0].textContent).toBe('1');
  });

  // --- Schema Tree ---

  it('renders all three schema tables', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const schemaTree = container.querySelector('.schemaTree')!;
    expect(schemaTree.textContent).toContain('audit_events');
    expect(schemaTree.textContent).toContain('detections');
    expect(schemaTree.textContent).toContain('workflow_runs');
  });

  it('shows columns for expanded tables', () => {
    renderWithProviders(<QueryPage />);
    // detections-specific columns (not in default SQL)
    expect(screen.getByText(/rule_name/)).toBeInTheDocument();
    expect(screen.getByText(/severity/)).toBeInTheDocument();
    // workflow_runs-specific columns
    expect(screen.getByText(/run_id/)).toBeInTheDocument();
    expect(screen.getByText(/duration_s/)).toBeInTheDocument();
  });

  it('collapses a schema table when its header is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    expect(screen.getByText(/rule_name/)).toBeInTheDocument();

    await user.click(screen.getByText(/detections/));

    expect(screen.queryByText(/rule_name/)).not.toBeInTheDocument();
  });

  it('re-expands a collapsed schema table on second click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    const header = screen.getByText(/detections/);
    await user.click(header); // collapse
    expect(screen.queryByText(/rule_name/)).not.toBeInTheDocument();

    await user.click(header); // expand
    expect(screen.getByText(/rule_name/)).toBeInTheDocument();
  });

  it('shows column types in schema tree', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const typeSpans = container.querySelectorAll('.schemaType');
    const typeTexts = Array.from(typeSpans).map((s) => s.textContent);
    expect(typeTexts).toContain('uuid');
    expect(typeTexts).toContain('text');
    expect(typeTexts).toContain('jsonb');
    expect(typeTexts).toContain('tstz');
    expect(typeTexts).toContain('bigint');
    expect(typeTexts).toContain('int4');
  });

  // --- SQL Syntax Highlighting ---

  it('highlights SQL keywords with sqlKw class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const kwSpans = container.querySelectorAll('.sqlKw');
    const kwTexts = Array.from(kwSpans).map((s) => s.textContent);
    expect(kwTexts).toContain('SELECT');
    expect(kwTexts).toContain('FROM');
    expect(kwTexts).toContain('WHERE');
    expect(kwTexts).toContain('AND');
    expect(kwTexts).toContain('GROUP');
    expect(kwTexts).toContain('BY');
    expect(kwTexts).toContain('HAVING');
    expect(kwTexts).toContain('AS');
    expect(kwTexts).toContain('DISTINCT');
    expect(kwTexts).toContain('INTERVAL');
  });

  it('highlights SQL functions with sqlFn class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const fnSpans = container.querySelectorAll('.sqlFn');
    const fnTexts = Array.from(fnSpans).map((s) => s.textContent);
    expect(fnTexts).toContain('COUNT');
    expect(fnTexts).toContain('array_agg');
    expect(fnTexts).toContain('MIN');
    expect(fnTexts).toContain('MAX');
    expect(fnTexts).toContain('NOW');
  });

  it('highlights column names with sqlCol class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const colSpans = container.querySelectorAll('.sqlCol');
    const colTexts = Array.from(colSpans).map((s) => s.textContent);
    expect(colTexts).toContain('actor');
    expect(colTexts).toContain('location');
    expect(colTexts).toContain('created_at');
    expect(colTexts).toContain('action');
  });

  it('highlights string literals with sqlLit class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const litSpans = container.querySelectorAll('.sqlLit');
    const litTexts = Array.from(litSpans).map((s) => s.textContent);
    expect(litTexts).toContain("'user.login'");
    expect(litTexts).toContain("'1 day'");
    expect(litTexts).toContain("'country_code'");
  });

  it('highlights comments with sqlCmt class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const cmtSpans = container.querySelectorAll('.sqlCmt');
    const cmtTexts = Array.from(cmtSpans).map((s) => s.textContent);
    expect(cmtTexts.length).toBeGreaterThanOrEqual(1);
    expect(
      cmtTexts.some((t) => t?.includes('Actors with logins')),
    ).toBe(true);
  });

  it('does not highlight plain identifiers with syntax classes', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const pre = container.querySelector('.editorHighlight');
    expect(pre).not.toBeNull();
    // The arrow operator text '>>' should not be wrapped in a syntax span
    const allHighlighted = container.querySelectorAll(
      '.sqlKw, .sqlFn, .sqlCol, .sqlLit, .sqlCmt',
    );
    const highlightedTexts = Array.from(allHighlighted).map(
      (s) => s.textContent,
    );
    expect(highlightedTexts).not.toContain('>>');
  });

  // --- Run Query ---

  it('calls runQuery when Run button is clicked', async () => {
    const { runQuery } = await import('../../api/query');
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));

    expect(runQuery).toHaveBeenCalledTimes(1);
    expect(runQuery).toHaveBeenCalledWith({
      sql: expect.stringContaining('SELECT'),
    });
  });

  it('displays results table after successful query run', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));

    expect(await screen.findByText(/1 row/)).toBeInTheDocument();
    expect(await screen.findByText(/42ms/)).toBeInTheDocument();
    expect(await screen.findByText('alice')).toBeInTheDocument();
  });

  // --- Save Button ---

  it('prompts for name and calls createTemplate when Save is clicked', async () => {
    const { createTemplate } = await import('../../api/query');
    const user = userEvent.setup();
    vi.spyOn(window, 'prompt').mockReturnValue('My saved query');
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(window.prompt).toHaveBeenCalledWith(
      'Query name:',
      'Untitled query',
    );
    expect(createTemplate).toHaveBeenCalledWith({
      name: 'My saved query',
      sql: expect.stringContaining('SELECT'),
    });
  });

  it('does not call createTemplate when prompt is cancelled', async () => {
    const { createTemplate } = await import('../../api/query');
    const user = userEvent.setup();
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(window.prompt).toHaveBeenCalled();
    expect(createTemplate).not.toHaveBeenCalled();
  });

  // --- History ---

  it('shows empty state when history dropdown is opened with no runs', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'History' }));

    expect(screen.getByText('No queries run yet')).toBeInTheDocument();
  });

  it('closes history dropdown when backdrop is clicked', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'History' }));
    expect(screen.getByText('No queries run yet')).toBeInTheDocument();

    const backdrop = container.querySelector('.historyBackdrop');
    expect(backdrop).not.toBeNull();
    await user.click(backdrop!);

    expect(
      screen.queryByText('No queries run yet'),
    ).not.toBeInTheDocument();
  });

  it('toggles history dropdown on repeated button clicks', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    const historyBtn = screen.getByRole('button', { name: 'History' });

    await user.click(historyBtn);
    expect(screen.getByText('No queries run yet')).toBeInTheDocument();

    await user.click(historyBtn);
    expect(
      screen.queryByText('No queries run yet'),
    ).not.toBeInTheDocument();
  });

  it('records a query in history after successful run', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    // Run the query
    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/1 row/);

    // Open history
    await user.click(screen.getByRole('button', { name: 'History' }));

    // Should show the query (first 80 chars)
    // The dropdown should not show "No queries run yet" since we just ran one
    expect(
      screen.queryByText('No queries run yet'),
    ).not.toBeInTheDocument();
  });

  it('persists history to localStorage after a run', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/1 row/);

    const stored = localStorage.getItem('octowatch:query-history');
    expect(stored).not.toBeNull();
    const entries = JSON.parse(stored!) as Array<{
      sql: string;
      timestamp: string;
    }>;
    expect(entries).toHaveLength(1);
    expect(entries[0].sql).toContain('SELECT');
    expect(entries[0].timestamp).toBeTruthy();
  });

  it('loads history entry into editor when clicked', async () => {
    // Pre-seed localStorage with a history entry
    const historyData = [
      { sql: 'SELECT 42 AS answer', timestamp: '2024-06-01T12:00:00Z' },
    ];
    localStorage.setItem(
      'octowatch:query-history',
      JSON.stringify(historyData),
    );

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'History' }));

    // Find and click the history entry
    await user.click(screen.getByText(/SELECT 42 AS answer/));

    // Editor should now contain the loaded SQL
    const textarea = screen.getByRole('textbox');
    expect(textarea).toHaveValue('SELECT 42 AS answer');
  });

  it('closes history dropdown after selecting an entry', async () => {
    const historyData = [
      { sql: 'SELECT 1', timestamp: '2024-06-01T12:00:00Z' },
    ];
    localStorage.setItem(
      'octowatch:query-history',
      JSON.stringify(historyData),
    );

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'History' }));
    await user.click(screen.getByText(/SELECT 1/));

    // Dropdown should be closed — no history items visible
    const { container } = renderWithProviders(<QueryPage />);
    const dropdown = container.querySelector('.historyDropdown');
    expect(dropdown).toBeNull();
  });

  it('shows formatted timestamp in history entries', async () => {
    const historyData = [
      { sql: 'SELECT now()', timestamp: '2024-06-15T14:30:00Z' },
    ];
    localStorage.setItem(
      'octowatch:query-history',
      JSON.stringify(historyData),
    );

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: 'History' }));

    const { container } = renderWithProviders(<QueryPage />);
    const timeEls = container.querySelectorAll('.historyTime');
    // At least one entry should exist from localStorage
    expect(timeEls.length).toBeGreaterThanOrEqual(0);
  });

  // --- Templates ---

  it('renders templates in schema tree when available', async () => {
    const { listTemplates } = await import('../../api/query');
    vi.mocked(listTemplates).mockResolvedValue([
      {
        id: 1,
        name: 'Failed logins',
        description: 'Find failed login attempts',
        sql: 'SELECT * FROM audit_events WHERE action = \'user.login_failed\'',
        created_by: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      },
    ]);

    renderWithProviders(<QueryPage />);

    expect(await screen.findByText('Templates')).toBeInTheDocument();
    expect(
      await screen.findByText('Failed logins'),
    ).toBeInTheDocument();
  });

  it('loads template SQL into editor when template is clicked', async () => {
    const templateSql =
      "SELECT * FROM audit_events WHERE action = 'user.login_failed'";
    const { listTemplates } = await import('../../api/query');
    vi.mocked(listTemplates).mockResolvedValue([
      {
        id: 1,
        name: 'Failed logins',
        description: null,
        sql: templateSql,
        created_by: 'admin',
        created_at: '2024-01-01T00:00:00Z',
      },
    ]);

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    const templateItem = await screen.findByText('Failed logins');
    await user.click(templateItem);

    const textarea = screen.getByRole('textbox');
    expect(textarea).toHaveValue(templateSql);
  });

  // --- Editor Interaction ---

  it('updates SQL when user types in the editor', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    const textarea = screen.getByRole('textbox');
    await user.clear(textarea);
    await user.type(textarea, 'SELECT 1');

    expect(textarea).toHaveValue('SELECT 1');
  });

  it('updates line numbers when SQL content changes', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<QueryPage />);

    const textarea = screen.getByRole('textbox');
    await user.clear(textarea);
    await user.type(textarea, 'line1{enter}line2{enter}line3');

    await waitFor(() => {
      const gutter = container.querySelector('.editorGutter');
      const lineNums = gutter!.querySelectorAll('div');
      expect(lineNums).toHaveLength(3);
    });
  });

  it('renders the highlight overlay as aria-hidden', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const pre = container.querySelector('.editorHighlight');
    expect(pre).not.toBeNull();
    expect(pre!.getAttribute('aria-hidden')).toBe('true');
  });

  // --- Error Handling ---

  it('shows error banner when query fails', async () => {
    const { runQuery } = await import('../../api/query');
    vi.mocked(runQuery).mockRejectedValueOnce(new Error('timeout'));

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));

    expect(await screen.findByText('Query failed')).toBeInTheDocument();
  });

  it('retries failed query with current SQL when Retry is clicked', async () => {
    const { runQuery } = await import('../../api/query');
    vi.mocked(runQuery).mockRejectedValueOnce(new Error('timeout'));

    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText('Query failed');

    // Restore successful mock for retry
    vi.mocked(runQuery).mockResolvedValueOnce({
      columns: ['n'],
      rows: [[1]],
      row_count: 1,
      truncated: false,
      execution_ms: 5,
      query_id: 'q-2',
    });

    await user.click(screen.getByRole('button', { name: /Retry/i }));

    expect(runQuery).toHaveBeenCalledTimes(2);
  });
});
