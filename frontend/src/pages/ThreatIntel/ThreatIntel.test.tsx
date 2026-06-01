import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ThreatIntelPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('../../api/threatIntel', () => ({
  listFeeds: vi.fn().mockResolvedValue({
    items: [
      {
        id: 1,
        name: 'AlienVault OTX',
        url: 'https://otx.alienvault.com/feed.txt',
        feed_type: 'domain',
        enabled: true,
        refresh_interval_minutes: 1440,
        last_fetched_at: '2024-06-15T10:00:00Z',
        last_fetch_status: 'success',
        last_indicator_count: 42,
        created_by: 'admin',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-06-15T10:00:00Z',
      },
      {
        id: 2,
        name: 'Blocklist.de',
        url: 'https://blocklist.de/lists/all.txt',
        feed_type: 'ip',
        enabled: false,
        refresh_interval_minutes: 720,
        last_fetched_at: null,
        last_fetch_status: null,
        last_indicator_count: null,
        created_by: 'admin',
        created_at: '2024-02-01T00:00:00Z',
        updated_at: '2024-02-01T00:00:00Z',
      },
    ],
  }),
  listIndicators: vi.fn().mockResolvedValue({
    items: [
      {
        id: 1,
        indicator_type: 'domain',
        value: 'malicious.example.com',
        source: 'manual',
        confidence: 0.9,
        active: true,
        added_at: '2024-06-01T00:00:00Z',
        added_by: 'analyst',
        expires_at: null,
        notes: 'Known phishing domain',
        feed_id: null,
        metadata_json: null,
      },
      {
        id: 2,
        indicator_type: 'ip',
        value: '10.0.0.1',
        source: 'feed:1',
        confidence: 0.7,
        active: true,
        added_at: '2024-06-10T00:00:00Z',
        added_by: 'system',
        expires_at: null,
        notes: null,
        feed_id: 1,
        metadata_json: null,
      },
    ],
    total: 2,
    page: 1,
    page_size: 50,
  }),
  listMatches: vi.fn().mockResolvedValue({
    items: [
      {
        detection_id: 101,
        title: 'Suspicious IP login',
        severity: 'high',
        status: 'open',
        actor: 'octocat',
        org: 'my-org',
        repo: null,
        triggered_at: '2024-06-15T12:00:00Z',
        matched_indicator_value: '10.0.0.1',
        matched_indicator_type: 'ip',
        matched_feed_name: 'AlienVault OTX',
      },
    ],
    total: 1,
    page: 1,
    page_size: 50,
    total_24h: 1,
    unique_indicators: 1,
    top_feed: 'AlienVault OTX',
  }),
  getAnalytics: vi.fn().mockResolvedValue({
    total_feeds: 2,
    active_feeds: 1,
    total_indicators: 42,
    active_indicators: 40,
    matches_30d: 5,
    coverage_score: 0.95,
    matches_over_time: [
      { date: '2024-06-14', count: 2 },
      { date: '2024-06-15', count: 3 },
    ],
    matches_by_feed: [{ name: 'AlienVault OTX', count: 30 }],
    indicator_type_distribution: [
      { type: 'domain', count: 25 },
      { type: 'ip', count: 15 },
    ],
  }),
  createFeed: vi.fn().mockResolvedValue({ id: 3, name: 'New Feed' }),
  updateFeed: vi.fn().mockResolvedValue({ id: 1, name: 'Updated Feed' }),
  deleteFeed: vi.fn().mockResolvedValue(undefined),
  refreshFeed: vi.fn().mockResolvedValue({ feed_id: 1, status: 'refreshing', message: 'ok' }),
  createIndicator: vi.fn().mockResolvedValue({ id: 3, value: 'new.example.com' }),
  deleteIndicator: vi.fn().mockResolvedValue(undefined),
  bulkCreateIndicators: vi.fn().mockResolvedValue({ created: 5, duplicates: 1, errors: 0 }),
}));

describe('ThreatIntelPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Tab rendering                                                     */
  /* ---------------------------------------------------------------- */

  it('renders page header and all tabs', () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    expect(screen.getByText('Threat Intelligence')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Feeds' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Indicators' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Matches' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Analytics' })).toBeInTheDocument();
  });

  it('shows Feeds tab as active by default', () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    const feedsTab = screen.getByRole('tab', { name: 'Feeds' });
    expect(feedsTab).toHaveAttribute('aria-selected', 'true');
  });

  it('renders feed data in the Feeds tab', async () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    expect(await screen.findByText('AlienVault OTX')).toBeInTheDocument();
    expect(screen.getByText('Blocklist.de')).toBeInTheDocument();
  });

  it('shows Add Feed button on Feeds tab', async () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await screen.findByText('AlienVault OTX');
    expect(screen.getByText('+ Add Feed')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Tab switching                                                     */
  /* ---------------------------------------------------------------- */

  it('switches to Indicators tab on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Indicators' }));

    expect(await screen.findByText('malicious.example.com')).toBeInTheDocument();
    expect(screen.getByText('10.0.0.1')).toBeInTheDocument();
  });

  it('switches to Matches tab and shows metric cards', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Matches' }));

    expect(await screen.findByText('Matches (24h)')).toBeInTheDocument();
    expect(screen.getByText('Unique Indicators Matched')).toBeInTheDocument();
    expect(screen.getByText('Suspicious IP login')).toBeInTheDocument();
  });

  it('switches to Analytics tab and shows metric cards', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Analytics' }));

    expect(await screen.findByText('Total Feeds')).toBeInTheDocument();
    expect(screen.getByText('Total Indicators')).toBeInTheDocument();
    expect(screen.getByText('Matches (30d)')).toBeInTheDocument();
    expect(screen.getByText('Coverage Score')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Feeds tab interactions                                            */
  /* ---------------------------------------------------------------- */

  it('opens Add Feed modal when clicking the button', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await screen.findByText('AlienVault OTX');
    await user.click(screen.getByText('+ Add Feed'));

    expect(screen.getByText('Add Feed')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. AlienVault OTX')).toBeInTheDocument();
  });

  it('shows feed status badges', async () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    expect(await screen.findByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Paused')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Feed detail drawer                                                */
  /* ---------------------------------------------------------------- */

  it('opens detail drawer when clicking a feed row', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await screen.findByText('AlienVault OTX');
    const row = screen.getByRole('button', { name: 'View details for AlienVault OTX' });
    await user.click(row);

    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });
    expect(screen.getByText('Feed Details')).toBeInTheDocument();
    // Drawer shows the feed URL as a link
    const drawerPanel = screen.getByTestId('drawer-panel');
    expect(drawerPanel.querySelector('a')).toHaveAttribute(
      'href',
      'https://otx.alienvault.com/feed.txt',
    );
  });

  it('closes detail drawer when clicking close button', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel/1',
      routePath: '/threat-intel/:feedId?',
    });

    // Wait for feed data and drawer to render
    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Close'));

    await waitFor(() => {
      expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
    });
  });

  it('opens feed detail via deep link URL', async () => {
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel/1',
      routePath: '/threat-intel/:feedId?',
    });

    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });
    expect(screen.getByText('Feed Details')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Indicators tab interactions                                       */
  /* ---------------------------------------------------------------- */

  it('shows search input on Indicators tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Indicators' }));

    expect(await screen.findByPlaceholderText('Search indicators…')).toBeInTheDocument();
  });

  it('shows Add Indicator button on Indicators tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Indicators' }));

    await screen.findByText('malicious.example.com');
    expect(screen.getByText('+ Add Indicator')).toBeInTheDocument();
  });

  it('shows Import CSV and Export buttons on Indicators tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Indicators' }));

    await screen.findByText('malicious.example.com');
    expect(screen.getByText('Import CSV')).toBeInTheDocument();
    expect(screen.getByText('Export')).toBeInTheDocument();
  });

  it('opens indicator detail drawer when clicking a row', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel?tab=indicators',
      routePath: '/threat-intel/:feedId?',
    });

    await screen.findByText('malicious.example.com');
    const row = screen.getByRole('button', { name: 'View details for malicious.example.com' });
    await user.click(row);

    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });
    expect(screen.getByText('Indicator Details')).toBeInTheDocument();
    // Verify the drawer panel contains the notes
    const drawerPanel = screen.getByTestId('drawer-panel');
    expect(drawerPanel).toHaveTextContent('Known phishing domain');
  });

  /* ---------------------------------------------------------------- */
  /*  Matches tab details                                               */
  /* ---------------------------------------------------------------- */

  it('shows match details with detection link', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Matches' }));

    const link = await screen.findByRole('link', { name: 'Suspicious IP login' });
    expect(link).toHaveAttribute('href', '/threats/open?id=101');
  });

  /* ---------------------------------------------------------------- */
  /*  Analytics tab charts                                              */
  /* ---------------------------------------------------------------- */

  it('shows analytics metric values', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ThreatIntelPage />, {
      route: '/threat-intel',
      routePath: '/threat-intel/:feedId?',
    });

    await user.click(screen.getByRole('tab', { name: 'Analytics' }));

    expect(await screen.findByText('Total Feeds')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument(); // total indicators
    expect(screen.getByText('95%')).toBeInTheDocument(); // coverage score
    expect(screen.getByText('Matches (30d)')).toBeInTheDocument();
  });
});
