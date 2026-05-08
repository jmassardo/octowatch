import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { EventsPage } from './index';
import { parseSearchFilters, downloadCsv } from './utils';
import type { EventResponse } from '../../types/events';

// ---------------------------------------------------------------------------
// Mock API
// ---------------------------------------------------------------------------

const MOCK_EVENTS: EventResponse[] = [
  {
    id: 1,
    document_id: 'doc-1',
    created_at: '2024-06-15T10:30:00Z',
    ingested_at: '2024-06-15T10:31:00Z',
    action: 'repo.create',
    namespace: 'repository',
    actor: 'alice',
    actor_id: 100,
    actor_is_bot: false,
    org: 'acme-corp',
    org_id: 200,
    repo: 'acme-corp/new-service',
    repo_id: 300,
    business: null,
    source_ip: '61.220.19.3',
    user_agent: 'Mozilla/5.0',
    geo_country_code: 'CN',
    geo_city: 'Beijing',
    geo_is_proxy: false,
    data: {},
    ingestion_source: 'webhook',
    source_file_path: '/events/1.json',
  },
  {
    id: 2,
    document_id: 'doc-2',
    created_at: '2024-06-15T11:00:00Z',
    ingested_at: '2024-06-15T11:01:00Z',
    action: 'repo.destroy',
    namespace: 'repository',
    actor: 'bob',
    actor_id: 101,
    actor_is_bot: false,
    org: 'acme-corp',
    org_id: 200,
    repo: 'acme-corp/old-service',
    repo_id: 301,
    business: null,
    source_ip: '192.168.1.1',
    user_agent: null,
    geo_country_code: 'US',
    geo_city: 'San Francisco',
    geo_is_proxy: null,
    data: { reason: 'cleanup' },
    ingestion_source: 'webhook',
    source_file_path: '/events/2.json',
  },
];

const listEventsMock = vi.fn().mockResolvedValue({
  items: MOCK_EVENTS,
  total: 2,
  page: 1,
  page_size: 20,
  has_next: false,
});

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => listEventsMock(...args),
  getEvent: vi.fn(),
  getRawEvent: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Unit tests – parseSearchFilters
// ---------------------------------------------------------------------------

describe('parseSearchFilters', () => {
  it('returns empty object for empty input', () => {
    expect(parseSearchFilters('')).toEqual({});
  });

  it('parses a single key:value token', () => {
    expect(parseSearchFilters('action:repo.create')).toEqual({ action: 'repo.create' });
  });

  it('parses multiple key:value tokens', () => {
    expect(parseSearchFilters('org:acme actor:alice')).toEqual({
      org: 'acme',
      actor: 'alice',
    });
  });

  it('maps "after" to "since" and "before" to "until"', () => {
    expect(parseSearchFilters('after:2024-01-01 before:2024-12-31')).toEqual({
      since: '2024-01-01',
      until: '2024-12-31',
    });
  });

  it('handles "since" and "until" directly', () => {
    expect(parseSearchFilters('since:2024-06-01 until:2024-06-30')).toEqual({
      since: '2024-06-01',
      until: '2024-06-30',
    });
  });

  it('parses repo key', () => {
    expect(parseSearchFilters('repo:acme-corp/my-repo')).toEqual({ repo: 'acme-corp/my-repo' });
  });

  it('ignores unrecognised keys', () => {
    expect(parseSearchFilters('foo:bar action:test')).toEqual({ action: 'test' });
  });

  it('handles mixed free text and key:value tokens', () => {
    expect(parseSearchFilters('some free text action:test more text')).toEqual({ action: 'test' });
  });

  it('preserves colons in timestamp values', () => {
    expect(parseSearchFilters('since:2024-01-01T00:00:00Z')).toEqual({
      since: '2024-01-01T00:00:00Z',
    });
  });

  it('last value wins when same key appears twice', () => {
    expect(parseSearchFilters('action:first action:second')).toEqual({ action: 'second' });
  });
});

// ---------------------------------------------------------------------------
// Unit tests – downloadCsv
// ---------------------------------------------------------------------------

describe('downloadCsv', () => {
  let clickSpy: ReturnType<typeof vi.fn>;
  let createObjectURLSpy: ReturnType<typeof vi.fn>;
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>;
  const originalCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    clickSpy = vi.fn();
    createObjectURLSpy = vi.fn().mockReturnValue('blob:mock-url');
    revokeObjectURLSpy = vi.fn();

    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectURLSpy,
      revokeObjectURL: revokeObjectURLSpy,
    });

    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { click: clickSpy, href: '', download: '' } as unknown as HTMLElement;
      }
      return originalCreateElement(tag);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('creates a CSV blob and triggers download', () => {
    downloadCsv(MOCK_EVENTS);

    expect(createObjectURLSpy).toHaveBeenCalledOnce();
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('text/csv;charset=utf-8;');

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url');
  });

  it('sets filename with current date', () => {
    downloadCsv(MOCK_EVENTS);

    const mockAnchor = (document.createElement as ReturnType<typeof vi.fn>).mock.results.find(
      (r: { type: string; value: unknown }) =>
        r.type === 'return' && (r.value as Record<string, unknown>).click === clickSpy,
    )?.value as { download: string } | undefined;

    const today = new Date().toISOString().slice(0, 10);
    expect(mockAnchor?.download).toBe(`octowatch-events-${today}.csv`);
  });

  it('produces correct CSV header and row count', async () => {
    downloadCsv(MOCK_EVENTS);

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();
    const lines = text.split('\n');

    // Header + 2 data rows
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe(
      '"Timestamp","Action","Actor","Repository","Organization","IP","Country"',
    );
  });

  it('escapes double quotes in cell values', async () => {
    const events: EventResponse[] = [
      {
        ...MOCK_EVENTS[0],
        action: 'test "quoted" action',
      },
    ];

    downloadCsv(events);

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();
    expect(text).toContain('"test ""quoted"" action"');
  });

  it('handles empty events array', () => {
    downloadCsv([]);

    expect(createObjectURLSpy).toHaveBeenCalledOnce();
    expect(clickSpy).toHaveBeenCalledOnce();
  });

  it('uses empty string for null fields', async () => {
    const events: EventResponse[] = [
      {
        ...MOCK_EVENTS[0],
        actor: null,
        repo: null,
        org: null,
        source_ip: null,
        geo_country_code: null,
      },
    ];

    downloadCsv(events);

    const blob = createObjectURLSpy.mock.calls[0][0] as Blob;
    const text = await blob.text();
    const dataRow = text.split('\n')[1];
    // Should contain empty quoted strings for null fields
    expect(dataRow).toContain('"","","","",""');
  });
});

// ---------------------------------------------------------------------------
// Component tests – EventsPage
// ---------------------------------------------------------------------------

describe('EventsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 2,
      page: 1,
      page_size: 20,
      has_next: false,
    });
  });

  it('renders page title and subtitle', () => {
    renderWithProviders(<EventsPage />);
    expect(screen.getByText('Events Explorer')).toBeInTheDocument();
    expect(
      screen.getByText('Search and explore raw audit log events across all organizations'),
    ).toBeInTheDocument();
  });

  it('renders the search bar with placeholder', () => {
    renderWithProviders(<EventsPage />);
    expect(
      screen.getByPlaceholderText('Search events... e.g. action:repo.create actor:@suspicious.*'),
    ).toBeInTheDocument();
  });

  it('renders events table with correct column headers', async () => {
    renderWithProviders(<EventsPage />);
    // Table headers only render after loading completes (DataTable is behind isLoading guard)
    expect(await screen.findByText('Timestamp')).toBeInTheDocument();
    expect(screen.getByText('Action')).toBeInTheDocument();
    expect(screen.getByText('Actor')).toBeInTheDocument();
    expect(screen.getByText('Repository')).toBeInTheDocument();
    expect(screen.getByText('IP / Location')).toBeInTheDocument();
  });

  it('displays event data in table rows after loading', async () => {
    renderWithProviders(<EventsPage />);

    expect(await screen.findByText('repo.create')).toBeInTheDocument();
    expect(screen.getByText('repo.destroy')).toBeInTheDocument();
    expect(screen.getByText('@alice')).toBeInTheDocument();
    expect(screen.getByText('@bob')).toBeInTheDocument();
    expect(screen.getByText('acme-corp/new-service')).toBeInTheDocument();
    expect(screen.getByText('acme-corp/old-service')).toBeInTheDocument();
  });

  it('displays IP and country code in the IP / Location column', async () => {
    renderWithProviders(<EventsPage />);

    expect(await screen.findByText('61.220.19.3')).toBeInTheDocument();
    expect(screen.getByText('CN')).toBeInTheDocument();
    expect(screen.getByText('192.168.1.1')).toBeInTheDocument();
    expect(screen.getByText('US')).toBeInTheDocument();
  });

  it('shows result count from API total', async () => {
    renderWithProviders(<EventsPage />);
    expect(await screen.findByText('2 events matching filters')).toBeInTheDocument();
  });

  it('shows formatted result count with thousands separator', async () => {
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 2847,
      page: 1,
      page_size: 20,
      has_next: true,
    });

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText('2,847 events matching filters')).toBeInTheDocument();
  });

  it('renders clickable rows for each event', async () => {
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.create');
    // Each event row should be present and clickable (table rows with onClick)
    const rows = screen.getAllByRole('row');
    // At least 3 rows: header + 2 data rows
    expect(rows.length).toBeGreaterThanOrEqual(3);
  });

  it('opens slide-out panel with event details when row is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.create');
    const actionLabel = screen.getByText('repo.create');
    const row = actionLabel.closest('tr')!;

    await user.click(row);

    // Panel header shows event action
    expect(screen.getAllByText('repo.create').length).toBeGreaterThanOrEqual(1);
    // EventDetail renders structured fields – check labels unique to the detail view
    expect(screen.getByText('Source IP')).toBeInTheDocument();
    expect(screen.getByText('Ingested')).toBeInTheDocument();
    expect(screen.getByText('Source')).toBeInTheDocument();
    // IP appears both in the table row and in the panel detail
    const ipElements = screen.getAllByText('61.220.19.3');
    expect(ipElements.length).toBeGreaterThanOrEqual(1);
  });

  it('closes slide-out panel when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.create');
    const actionLabel = screen.getByText('repo.create');
    const row = actionLabel.closest('tr')!;

    await user.click(row);
    // Panel is open — detail-specific fields should be visible
    expect(screen.getByText('Source IP')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Close'));
    // Panel closed — detail fields should be gone
    expect(screen.queryByText('Source IP')).not.toBeInTheDocument();
  });

  it('adds a chip when Enter is pressed in search bar', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    const input = screen.getByPlaceholderText(
      'Search events... e.g. action:repo.create actor:@suspicious.*',
    );
    await user.type(input, 'action:repo.create{enter}');

    // Chip should appear
    expect(screen.getByText('action:repo.create')).toBeInTheDocument();
    // Input should be cleared
    expect(input).toHaveValue('');
  });

  it('passes chip params to listEvents API', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.create');

    const input = screen.getByPlaceholderText(
      'Search events... e.g. action:repo.create actor:@suspicious.*',
    );
    await user.type(input, 'org:acme-corp{enter}');

    // Wait for the query to be called with the chip param
    await screen.findByText('repo.create');
    const lastCall = listEventsMock.mock.calls[listEventsMock.mock.calls.length - 1];
    expect(lastCall[0]).toMatchObject({ org: 'acme-corp' });
  });

  it('removes chip when × is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    const input = screen.getByPlaceholderText(
      'Search events... e.g. action:repo.create actor:@suspicious.*',
    );
    await user.type(input, 'action:test{enter}');
    expect(screen.getByText('action:test')).toBeInTheDocument();

    // Click the × on the chip
    const chipCloseButton = screen.getByText('×');
    await user.click(chipCloseButton);
    expect(screen.queryByText('action:test')).not.toBeInTheDocument();
  });

  it('disables Export CSV button when no events', async () => {
    listEventsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithProviders(<EventsPage />);

    await screen.findByText('No events found');
    const exportBtn = screen.getByRole('button', { name: 'Export CSV' });
    expect(exportBtn).toBeDisabled();
  });

  it('enables Export CSV button when events exist', async () => {
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.create');
    const exportBtn = screen.getByRole('button', { name: 'Export CSV' });
    expect(exportBtn).not.toBeDisabled();
  });

  it('shows "No events found" when API returns empty list', async () => {
    listEventsMock.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText('No events found')).toBeInTheDocument();
  });

  it('shows error banner when API fails', async () => {
    listEventsMock.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText('Failed to load events')).toBeInTheDocument();
  });

  it('renders pagination when total exceeds page size', async () => {
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 100,
      page: 1,
      page_size: 20,
      has_next: true,
      count_is_estimated: false,
      next_cursor: 'cursor_abc',
    });

    renderWithProviders(<EventsPage />);
    await screen.findByText('repo.create');

    expect(screen.getByText('Page 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '← Prev' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next →' })).not.toBeDisabled();
  });

  it('does not render pagination when total fits in one page', async () => {
    renderWithProviders(<EventsPage />);
    await screen.findByText('repo.create');

    expect(screen.queryByText(/^Page \d+$/)).not.toBeInTheDocument();
  });

  it('chip parser handles repo, since, and until keys', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);
    await screen.findByText('repo.create');

    const input = screen.getByPlaceholderText(
      'Search events... e.g. action:repo.create actor:@suspicious.*',
    );

    await user.type(input, 'repo:acme/service{enter}');
    await screen.findByText('repo.create');

    const lastCall = listEventsMock.mock.calls[listEventsMock.mock.calls.length - 1];
    expect(lastCall[0]).toMatchObject({ repo: 'acme/service' });
  });

  it('renders Export CSV and Save query buttons', () => {
    renderWithProviders(<EventsPage />);
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save query' })).toBeInTheDocument();
  });

  it('renders Export CSV and search input for filtering', () => {
    renderWithProviders(<EventsPage />);
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('Search events... e.g. action:repo.create actor:@suspicious.*'),
    ).toBeInTheDocument();
  });

  it('navigates pages when Next and Prev are clicked', async () => {
    const user = userEvent.setup();
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 60,
      page: 1,
      page_size: 20,
      has_next: true,
      count_is_estimated: false,
      next_cursor: 'cursor_page2',
    });

    renderWithProviders(<EventsPage />);
    await screen.findByText('Page 1');

    await user.click(screen.getByRole('button', { name: 'Next →' }));

    // Should call API with cursor param
    const callsWithCursor = listEventsMock.mock.calls.filter(
      (call: unknown[]) => (call[0] as Record<string, unknown>).cursor === 'cursor_page2',
    );
    expect(callsWithCursor.length).toBeGreaterThan(0);
  });

  it('shows the second event details when its row is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EventsPage />);

    await screen.findByText('repo.destroy');
    const actionLabel = screen.getByText('repo.destroy');
    const row = actionLabel.closest('tr')!;

    await user.click(row);

    // Panel header shows event action
    expect(screen.getAllByText('repo.destroy').length).toBeGreaterThanOrEqual(1);
    // EventDetail renders structured fields – check the detail-only labels
    expect(screen.getByText('Source IP')).toBeInTheDocument();
    // IP appears both in the table and in the panel
    const ipElements = screen.getAllByText('192.168.1.1');
    expect(ipElements.length).toBeGreaterThanOrEqual(1);
    // Additional Data section should be present because this event has data.reason
    expect(screen.getByText('Additional Data')).toBeInTheDocument();
    expect(screen.getByText('reason')).toBeInTheDocument();
    expect(screen.getByText('cleanup')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // URL query param initialization
  // -------------------------------------------------------------------------

  it('initializes chips from URL query params on mount', async () => {
    renderWithProviders(<EventsPage />, { route: '/events?repo=my-repo' });

    // The chip should appear in the filter area
    expect(await screen.findByText('repo:my-repo')).toBeInTheDocument();
  });

  it('initializes multiple chips from URL query params', async () => {
    renderWithProviders(<EventsPage />, {
      route: '/events?repo=my-repo&actor=alice',
    });

    expect(await screen.findByText('repo:my-repo')).toBeInTheDocument();
    expect(screen.getByText('actor:alice')).toBeInTheDocument();
  });

  it('passes URL-sourced chip filters to the API call', async () => {
    renderWithProviders(<EventsPage />, { route: '/events?repo=my-repo' });

    await screen.findByText('repo:my-repo');

    // The listEvents mock should have been called with the repo filter
    expect(listEventsMock).toHaveBeenCalledWith(expect.objectContaining({ repo: 'my-repo' }));
  });

  it('ignores unsupported URL query params', () => {
    renderWithProviders(<EventsPage />, { route: '/events?unsupported=value' });

    // No chip should appear for unsupported params
    const chips = screen.queryAllByText(/unsupported:value/);
    expect(chips).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // URL since/until param initialization
  // -------------------------------------------------------------------------

  it('initializes since chip from URL query param', async () => {
    renderWithProviders(<EventsPage />, { route: '/events?since=2024-06-01' });

    expect(await screen.findByText('since:2024-06-01')).toBeInTheDocument();
  });

  it('initializes until chip from URL query param', async () => {
    renderWithProviders(<EventsPage />, { route: '/events?until=2024-06-30' });

    expect(await screen.findByText('until:2024-06-30')).toBeInTheDocument();
  });

  it('initializes both since and until chips from URL query params', async () => {
    renderWithProviders(<EventsPage />, {
      route: '/events?since=2024-06-01&until=2024-06-30',
    });

    expect(await screen.findByText('since:2024-06-01')).toBeInTheDocument();
    expect(screen.getByText('until:2024-06-30')).toBeInTheDocument();
  });

  it('passes since/until from URL chips to the API call', async () => {
    renderWithProviders(<EventsPage />, {
      route: '/events?since=2024-06-01&until=2024-06-30',
    });

    await screen.findByText('since:2024-06-01');

    expect(listEventsMock).toHaveBeenCalledWith(
      expect.objectContaining({ since: '2024-06-01', until: '2024-06-30' }),
    );
  });

  it('combines since/until with other URL params as chips', async () => {
    renderWithProviders(<EventsPage />, {
      route: '/events?actor=alice&since=2024-06-01&until=2024-06-30',
    });

    expect(await screen.findByText('actor:alice')).toBeInTheDocument();
    expect(screen.getByText('since:2024-06-01')).toBeInTheDocument();
    expect(screen.getByText('until:2024-06-30')).toBeInTheDocument();

    expect(listEventsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        actor: 'alice',
        since: '2024-06-01',
        until: '2024-06-30',
      }),
    );
  });

  it('shows approximate count when count_is_estimated is true', async () => {
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 15000,
      page: 1,
      page_size: 20,
      has_next: true,
      count_is_estimated: true,
      next_cursor: null,
    });

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText(/≈ 15,000 events matching filters/)).toBeInTheDocument();
  });

  it('shows 500,000+ for very large estimated counts', async () => {
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 750000,
      page: 1,
      page_size: 20,
      has_next: true,
      count_is_estimated: true,
      next_cursor: null,
    });

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText(/500,000\+ events matching filters/)).toBeInTheDocument();
  });

  it('shows large result guidance when total exceeds 5000', async () => {
    listEventsMock.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 10000,
      page: 1,
      page_size: 20,
      has_next: true,
      count_is_estimated: false,
      next_cursor: null,
    });

    renderWithProviders(<EventsPage />);
    expect(await screen.findByText(/Showing first 5,000 results/)).toBeInTheDocument();
  });
});
