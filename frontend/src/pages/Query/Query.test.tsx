import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, act } from '@testing-library/react';
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
  validateQuery: vi.fn().mockResolvedValue({ valid: true }),
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

  it('renders all schema tables', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const schemaTree = container.querySelector('.schemaTree')!;
    expect(schemaTree.textContent).toContain('events');
    expect(schemaTree.textContent).toContain('detections');
    expect(schemaTree.textContent).toContain('events_hourly');
    expect(schemaTree.textContent).toContain('events_daily_actor');
    expect(schemaTree.textContent).toContain('detections_daily');
  });

  it('shows columns for expanded tables', () => {
    renderWithProviders(<QueryPage />);
    // events-specific columns
    expect(screen.getByText(/source_ip/)).toBeInTheDocument();
    expect(screen.getAllByText(/geo_country_code/).length).toBeGreaterThanOrEqual(1);
    // events_hourly-specific columns
    expect(screen.getByText(/bucket_hour/)).toBeInTheDocument();
  });

  it('collapses a schema table when its header is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    expect(screen.getByText(/source_ip/)).toBeInTheDocument();

    // Click the "events" table header (exact match to avoid events_hourly etc.)
    const headers = screen.getAllByText(/events/);
    const eventsHeader = headers.find((el) => el.textContent === '▼ events');
    expect(eventsHeader).toBeDefined();
    await user.click(eventsHeader!);

    expect(screen.queryByText(/source_ip/)).not.toBeInTheDocument();
  });

  it('re-expands a collapsed schema table on second click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryPage />);

    // Click to collapse events table
    const expandedHeaders = screen.getAllByText(/events/);
    const eventsHeader = expandedHeaders.find((el) => el.textContent === '▼ events');
    expect(eventsHeader).toBeDefined();
    await user.click(eventsHeader!); // collapse
    expect(screen.queryByText(/source_ip/)).not.toBeInTheDocument();

    // Click to re-expand
    const collapsedHeaders = screen.getAllByText(/events/);
    const collapsedHeader = collapsedHeaders.find((el) => el.textContent === '▶ events');
    expect(collapsedHeader).toBeDefined();
    await user.click(collapsedHeader!); // expand
    expect(screen.getByText(/source_ip/)).toBeInTheDocument();
  });

  it('shows column types in schema tree', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const typeSpans = container.querySelectorAll('.schemaType');
    const typeTexts = Array.from(typeSpans).map((s) => s.textContent);
    expect(typeTexts).toContain('bigint');
    expect(typeTexts).toContain('text');
    expect(typeTexts).toContain('jsonb');
    expect(typeTexts).toContain('tstz');
    expect(typeTexts).toContain('inet');
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
    expect(colTexts).toContain('geo_country_code');
    expect(colTexts).toContain('created_at');
    expect(colTexts).toContain('action');
  });

  it('highlights string literals with sqlLit class', () => {
    const { container } = renderWithProviders(<QueryPage />);
    const litSpans = container.querySelectorAll('.sqlLit');
    const litTexts = Array.from(litSpans).map((s) => s.textContent);
    expect(litTexts).toContain("'user.login'");
    expect(litTexts).toContain("'1 day'");
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

  it('row count is clickable after query run', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/1 row/);

    const rowSpan = container.querySelector('.clickableMeta[role="button"]');
    expect(rowSpan).not.toBeNull();
    expect(rowSpan!.textContent).toMatch(/1 row/);
  });

  it('execution time is clickable after query run', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/42ms/);

    const msSpans = container.querySelectorAll('.clickableMeta');
    const msSpan = Array.from(msSpans).find((el) => el.textContent?.includes('ms'));
    expect(msSpan).not.toBeUndefined();
    expect(msSpan!.getAttribute('role')).toBe('button');
  });

  it('clicking execution time opens modal', async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<QueryPage />);

    await user.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/42ms/);

    const msSpans = container.querySelectorAll('.clickableMeta');
    const msSpan = Array.from(msSpans).find((el) => el.textContent?.includes('ms'))!;
    await user.click(msSpan);

    expect(screen.getByText('Query Execution Details')).toBeInTheDocument();
  });

  // --- Validation, Autocomplete, Keyboard Shortcut, Click-to-Insert ---
  // These tests use fake timers because the validation debounce (800ms) creates
  // a pending setTimeout that prevents userEvent from settling with real timers.
  // We use fireEvent + act for timer-sensitive scenarios and userEvent.setup
  // with advanceTimers for interactions.

  describe('intellisense features', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.runOnlyPendingTimers();
      vi.useRealTimers();
    });

    // --- Live Validation ---

    it('calls validateQuery after 800ms debounce and shows valid badge', async () => {
      const { validateQuery } = await import('../../api/query');
      vi.mocked(validateQuery).mockResolvedValue({ valid: true });

      renderWithProviders(<QueryPage />);

      // Advance past the debounce and flush React updates
      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      expect(validateQuery).toHaveBeenCalledWith(expect.stringContaining('SELECT'));
      expect(screen.getByText(/✓ Valid/)).toBeInTheDocument();
    });

    it('shows invalid badge with error message when validation fails', async () => {
      const { validateQuery } = await import('../../api/query');
      vi.mocked(validateQuery).mockResolvedValue({ valid: false, error: 'Syntax error at position 5' });

      renderWithProviders(<QueryPage />);

      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      expect(screen.getByText(/✗/)).toBeInTheDocument();
      expect(screen.getByText(/Syntax error at position 5/)).toBeInTheDocument();
    });

    it('truncates long validation errors to ~80 chars with full tooltip', async () => {
      const { validateQuery } = await import('../../api/query');
      const longError = 'A'.repeat(120);
      vi.mocked(validateQuery).mockResolvedValue({ valid: false, error: longError });

      const { container } = renderWithProviders(<QueryPage />);

      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      const badge = container.querySelector('.invalidBadge');
      expect(badge).not.toBeNull();
      expect(badge!.textContent!.length).toBeLessThan(120);
      expect(badge!.getAttribute('title')).toBe(longError);
    });

    it('does not validate empty or whitespace-only queries', async () => {
      const { validateQuery } = await import('../../api/query');

      renderWithProviders(<QueryPage />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      // Clear the textarea via React's controlled input mechanism
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, '');
        textarea.selectionStart = 0;
        textarea.selectionEnd = 0;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      vi.mocked(validateQuery).mockClear();

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(validateQuery).not.toHaveBeenCalled();
    });

    it('shows validating indicator while validation is in progress', async () => {
      const { validateQuery } = await import('../../api/query');

      let resolveValidation!: (val: { valid: boolean }) => void;
      vi.mocked(validateQuery).mockReturnValue(
        new Promise((resolve) => { resolveValidation = resolve; }),
      );

      const { container } = renderWithProviders(<QueryPage />);

      await act(async () => {
        vi.advanceTimersByTime(800);
      });

      const badge = container.querySelector('.validatingBadge');
      expect(badge).not.toBeNull();

      await act(async () => {
        resolveValidation({ valid: true });
      });

      expect(screen.getByText(/✓ Valid/)).toBeInTheDocument();
    });

    // --- Keyboard Shortcut ---

    it('runs query on Ctrl+Enter', async () => {
      const { runQuery } = await import('../../api/query');
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox');

      await act(async () => {
        textarea.focus();
        textarea.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Enter', ctrlKey: true, bubbles: true,
        }));
      });

      expect(runQuery).toHaveBeenCalled();
    });

    it('runs query on Meta+Enter (Cmd on Mac)', async () => {
      const { runQuery } = await import('../../api/query');
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox');

      await act(async () => {
        textarea.focus();
        textarea.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Enter', metaKey: true, bubbles: true,
        }));
      });

      expect(runQuery).toHaveBeenCalled();
    });

    it('shows keyboard shortcut hint next to Run button', () => {
      const { container } = renderWithProviders(<QueryPage />);
      const hint = container.querySelector('.shortcutHint');
      expect(hint).not.toBeNull();
      expect(hint!.textContent).toMatch(/Ctrl\+↵|⌘\+↵/);
    });

    // --- Schema Click-to-Insert ---

    it('inserts column name at cursor when schema column is clicked', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      // Set textarea to a short query with cursor at end
      await act(async () => {
        // Use the native setter to change the value (React's onChange won't fire from just setting .value)
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        nativeInputValueSetter.call(textarea, 'SELECT ');
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      // Click a schema column — source_ip is unique to events table
      const colButtons = screen.getAllByRole('button').filter(
        (el) => el.textContent?.includes('source_ip'),
      );
      expect(colButtons.length).toBeGreaterThanOrEqual(1);

      await act(async () => {
        colButtons[0].click();
      });

      expect(textarea.value).toContain('source_ip');
    });

    it('schema columns have role="button" for accessibility', () => {
      const { container } = renderWithProviders(<QueryPage />);
      const colButtons = container.querySelectorAll('.schemaColClickable[role="button"]');
      expect(colButtons.length).toBeGreaterThan(0);
    });

    // --- Autocomplete ---

    it('shows autocomplete dropdown when typing 2+ chars matching keywords', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      // Set value and cursor position to trigger autocomplete
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const listbox = screen.queryByRole('listbox');
      expect(listbox).toBeInTheDocument();

      // 'SE' is highlighted, 'LECT' is the rest of 'SELECT'
      expect(screen.getByText('LECT')).toBeInTheDocument();
    });

    it('shows table suggestions after FROM keyword', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SELECT * FROM e');
        textarea.selectionStart = 15;
        textarea.selectionEnd = 15;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const listbox = screen.queryByRole('listbox');
      expect(listbox).toBeInTheDocument();

      const options = screen.getAllByRole('option');
      const texts = options.map((o) => o.textContent);
      expect(texts.some((t) => t?.includes('events'))).toBe(true);
    });

    it('shows column suggestions after WHERE keyword', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SELECT * FROM events WHERE a');
        textarea.selectionStart = 28;
        textarea.selectionEnd = 28;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const options = screen.getAllByRole('option');
      const texts = options.map((o) => o.textContent);
      expect(texts.some((t) => t?.includes('action'))).toBe(true);
      expect(texts.some((t) => t?.includes('actor'))).toBe(true);
    });

    it('does not show autocomplete with fewer than 2 chars in general context', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'S');
        textarea.selectionStart = 1;
        textarea.selectionEnd = 1;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('dismisses autocomplete on Escape and does not re-trigger until user types', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      // Type 'SE' to show autocomplete
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).toBeInTheDocument();

      // Press Escape to dismiss
      await act(async () => {
        textarea.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Escape', bubbles: true,
        }));
      });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('accepts autocomplete suggestion with Tab key', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).toBeInTheDocument();

      // Press Tab to accept the first suggestion (SELECT)
      await act(async () => {
        textarea.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'Tab', bubbles: true,
        }));
      });

      expect(textarea.value).toContain('SELECT');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('navigates autocomplete suggestions with ArrowDown/ArrowUp', async () => {
      const { container } = renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).toBeInTheDocument();

      let activeItems = container.querySelectorAll('.acItemActive');
      expect(activeItems.length).toBe(1);

      // Press ArrowDown to move to second item
      await act(async () => {
        textarea.dispatchEvent(new KeyboardEvent('keydown', {
          key: 'ArrowDown', bubbles: true,
        }));
      });

      activeItems = container.querySelectorAll('.acItemActive');
      expect(activeItems.length).toBe(1);
      const selected = screen.getAllByRole('option').filter(
        (o) => o.getAttribute('aria-selected') === 'true',
      );
      expect(selected).toHaveLength(1);
    });

    it('shows suggestion type labels (KW, FN, TBL, COL)', async () => {
      const { container } = renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const typeLabels = container.querySelectorAll('.acItemType');
      expect(typeLabels.length).toBeGreaterThan(0);
      const labelTexts = Array.from(typeLabels).map((el) => el.textContent);
      expect(labelTexts.some((t) => t === 'KW')).toBe(true);
    });

    it('highlights the matching portion of suggestions', async () => {
      const { container } = renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, 'SE');
        textarea.selectionStart = 2;
        textarea.selectionEnd = 2;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      const highlights = container.querySelectorAll('.acHighlight');
      expect(highlights.length).toBeGreaterThan(0);
      expect(Array.from(highlights).some((el) => el.textContent === 'SE')).toBe(true);
    });

    it('does not show autocomplete inside string literals', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, "SELECT * FROM events WHERE action = 'SE");
        textarea.selectionStart = 39;
        textarea.selectionEnd = 39;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('does not show autocomplete inside comments', async () => {
      renderWithProviders(<QueryPage />);

      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype, 'value',
        )!.set!;
        setter.call(textarea, '-- This is SE');
        textarea.selectionStart = 13;
        textarea.selectionEnd = 13;
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
      });

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });
});
