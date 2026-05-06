import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ThreatsPage } from './index';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockListDetections = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockUpdateDetectionStatus = vi.fn().mockResolvedValue({});
const mockDeleteDetection = vi.fn().mockResolvedValue({});
const mockAssignDetection = vi.fn().mockResolvedValue({});

vi.mock('../../api/detections', () => ({
  listDetections: (...args: unknown[]) => mockListDetections(...args),
  updateDetectionStatus: (...args: unknown[]) => mockUpdateDetectionStatus(...args),
  deleteDetection: (...args: unknown[]) => mockDeleteDetection(...args),
  assignDetection: (...args: unknown[]) => mockAssignDetection(...args),
}));

describe('ThreatsPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockListDetections.mockClear();
    mockListDetections.mockResolvedValue({ items: [], total: 0 });
  });

  /* ---------------------------------------------------------------- */
  /*  Page header                                                      */
  /* ---------------------------------------------------------------- */

  it('renders the page title', () => {
    renderWithProviders(<ThreatsPage />);
    expect(screen.getByText('Threat Detections')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    renderWithProviders(<ThreatsPage />);
    expect(screen.getByText(/rule-based and ml-powered/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Tab buttons                                                      */
  /* ---------------------------------------------------------------- */

  it('renders all five tabs', () => {
    renderWithProviders(<ThreatsPage />);
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Investigating')).toBeInTheDocument();
    expect(screen.getByText('Closed')).toBeInTheDocument();
    expect(screen.getByText('Acknowledged')).toBeInTheDocument();
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  it('renders tab count badges when data is loaded', async () => {
    mockListDetections.mockResolvedValue({ items: [], total: 5 });
    renderWithProviders(<ThreatsPage />);

    // All tabs fetch counts so badges should appear
    const badges = await screen.findAllByText('5');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('switches tab on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const closedTab = screen.getByText('Closed');
    await user.click(closedTab);

    // Tab should be clickable — the API is called with the new status
    expect(mockListDetections).toHaveBeenCalled();
  });

  /* ---------------------------------------------------------------- */
  /*  Empty state                                                      */
  /* ---------------------------------------------------------------- */

  it('renders contextual empty state for open tab when no detections', async () => {
    renderWithProviders(<ThreatsPage />);
    expect(await screen.findByText('No open threats detected')).toBeInTheDocument();
  });

  it('renders contextual empty state for closed tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const closedTab = screen.getByText('Closed');
    await user.click(closedTab);

    expect(await screen.findByText('No closed detections')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Filter button                                                    */
  /* ---------------------------------------------------------------- */

  it('filter controls are always visible', () => {
    renderWithProviders(<ThreatsPage />);

    // Severity filter dropdown should always be visible (no toggle button)
    expect(screen.getByDisplayValue('All severities')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Tests with populated data                                          */
/* ------------------------------------------------------------------ */

describe('ThreatsPage with data', () => {
  const MOCK_DETECTION = {
    id: 1,
    rule_id: 10,
    rule_name: 'suspicious_admin_action',
    rule_version: 1,
    severity: 'critical' as const,
    confidence: 'high',
    confidence_score: 0.95,
    status: 'investigating' as const,
    title: 'Suspicious admin activity detected',
    description: 'Admin action from unusual IP',
    actor: 'mallory',
    org: 'myorg',
    repo: null,
    source_ip: '1.2.3.4',
    window_start: null,
    window_end: null,
    event_ids: [101, 102, 103],
    context_data: { ip: '1.2.3.4', action: 'org.update_member' },
    triggered_at: '2024-01-15T12:00:00Z',
    assigned_to: null,
    resolved_at: null,
    resolution_note: null,
    tickets: [],
  };

  beforeEach(() => {
    mockNavigate.mockClear();
    mockListDetections.mockClear();
    mockListDetections.mockResolvedValue({
      items: [MOCK_DETECTION],
      total: 1,
      page: 1,
      page_size: 50,
      has_next: false,
    });
  });

  it('renders detection rows from API data', async () => {
    renderWithProviders(<ThreatsPage />);
    expect(await screen.findByText('Suspicious admin activity detected')).toBeInTheDocument();
  });

  it('opens detail panel when a detection row is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    // Detail panel should show description
    expect(screen.getByText('Admin action from unusual IP')).toBeInTheDocument();
  });

  it('shows related events count as a clickable link in detail panel', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    const link = screen.getByText('3 events →');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('role', 'button');
  });

  it('navigates to events page when related events count is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    const link = screen.getByText('3 events →');
    await user.click(link);

    expect(mockNavigate).toHaveBeenCalledWith(expect.stringContaining('/events?'));
    // Should include actor param
    expect(mockNavigate).toHaveBeenCalledWith(expect.stringContaining('actor=mallory'));
  });

  it('renders evidence section for detection with context data', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    expect(screen.getByText('Evidence')).toBeInTheDocument();
  });

  it('shows severity and rule labels in detail panel', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    // Panel shows severity, rule name, and confidence labels
    const panelEl = screen.getByText('Admin action from unusual IP').closest('div');
    expect(panelEl).toBeInTheDocument();

    // Check that the panel section has the labels (may appear in both list and panel)
    const labels = screen.getAllByText('critical');
    expect(labels.length).toBeGreaterThanOrEqual(1);
    const ruleLabels = screen.getAllByText('suspicious_admin_action');
    expect(ruleLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('renders action buttons in the detail panel', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    expect(screen.getByText('Delete Detection')).toBeInTheDocument();
    expect(screen.getByText('Acknowledge')).toBeInTheDocument();
    expect(screen.getByText('Assign')).toBeInTheDocument();
  });

  it('shows actor mention in detection row', async () => {
    renderWithProviders(<ThreatsPage />);
    expect(await screen.findByText('@mallory')).toBeInTheDocument();
  });

  it('closes detail panel when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatsPage />);

    const row = await screen.findByText('Suspicious admin activity detected');
    await user.click(row);

    // Detail panel should be open
    expect(screen.getByText('Admin action from unusual IP')).toBeInTheDocument();

    // Click close button
    const closeBtn = screen.getByText('×');
    await user.click(closeBtn);

    // Description should no longer be visible (panel closes)
    // The splitPanel hides via CSS display:none but in tests the element may still be in DOM
    // We check the panel container doesn't have the 'open' class behavior
    const panels = document.querySelectorAll('[class*="splitPanel"]');
    const openPanels = [...panels].filter((p) => p.className.includes('open'));
    expect(openPanels).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// URL severity param initialization
// ---------------------------------------------------------------------------

describe('ThreatsPage severity URL param', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockListDetections.mockClear();
    mockListDetections.mockResolvedValue({ items: [], total: 0 });
  });

  it('initializes severity filter from URL search params', async () => {
    renderWithProviders(<ThreatsPage />, { route: '/threats?severity=critical' });

    // Filter panel should be visible since severity was provided via URL
    expect(screen.getByDisplayValue('Critical')).toBeInTheDocument();

    // API should be called with the severity filter from URL
    expect(mockListDetections).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'critical' }),
    );
  });

  it('auto-opens filter panel when severity is provided via URL', () => {
    renderWithProviders(<ThreatsPage />, { route: '/threats?severity=high' });

    // The severity dropdown should be visible without clicking the Filter button
    expect(screen.getByDisplayValue('High')).toBeInTheDocument();
  });

  it('defaults to empty severity filter when no URL param is present', () => {
    renderWithProviders(<ThreatsPage />);

    // Filter panel is always visible; severity defaults to "All severities"
    expect(screen.getByDisplayValue('All severities')).toBeInTheDocument();
  });

  it('passes severity from URL to the detections API query', async () => {
    renderWithProviders(<ThreatsPage />, { route: '/threats?severity=medium' });

    // Wait for queries to fire
    await screen.findByText(/no open threats|Threat Detections/i);

    const callsWithMedium = mockListDetections.mock.calls.filter(
      (call: unknown[]) => (call[0] as Record<string, unknown>).severity === 'medium',
    );
    expect(callsWithMedium.length).toBeGreaterThan(0);
  });
});

describe('ThreatsPage tab count badges', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockListDetections.mockClear();
  });

  it('shows different counts for different tabs', async () => {
    // Mock returns different totals based on status param
    mockListDetections.mockImplementation((params: Record<string, unknown>) => {
      if (params.status === 'open') return Promise.resolve({ items: [], total: 5 });
      if (params.status === 'investigating') return Promise.resolve({ items: [], total: 3 });
      if (params.status === 'resolved') return Promise.resolve({ items: [], total: 7 });
      if (params.status === 'false_positive') return Promise.resolve({ items: [], total: 2 });
      return Promise.resolve({ items: [], total: 17 });
    });

    renderWithProviders(<ThreatsPage />);

    // Wait for tab counts to appear
    expect(await screen.findByText('5')).toBeInTheDocument();
    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(await screen.findByText('7')).toBeInTheDocument();
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(await screen.findByText('17')).toBeInTheDocument();

    // Verify the badges are inside tab buttons
    const openTab = screen.getByText('Open').closest('button');
    expect(openTab).toBeInTheDocument();
    expect(within(openTab!).getByText('5')).toBeInTheDocument();
  });
});
