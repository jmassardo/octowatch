import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PackagesPage } from './index';
import type {
  PackageSummary,
  PackageAlertList,
  PackageInventory,
  StaleImageList,
} from '../../api/packages';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockSummary: PackageSummary = {
  total_packages: 25,
  public_packages: 3,
  private_packages: 22,
  by_type: { npm: 10, docker: 8, maven: 5, nuget: 2 },
  newly_public: 1,
  stale_images: 2,
  open_alerts: 4,
};

const mockAlerts: PackageAlertList = {
  alerts: [
    {
      id: 1,
      package_id: 10,
      package_name: 'my-public-pkg',
      package_org: 'my-org',
      alert_type: 'public_exposure',
      severity: 'high',
      message: "Package 'my-public-pkg' has public visibility",
      detected_at: '2024-01-15T10:00:00Z',
      resolved_at: null,
      status: 'open',
    },
    {
      id: 2,
      package_id: 11,
      package_name: 'old-image',
      package_org: 'my-org',
      alert_type: 'stale_image',
      severity: 'medium',
      message: "Container image 'old-image' not rebuilt in 120 days",
      detected_at: '2024-01-10T10:00:00Z',
      resolved_at: null,
      status: 'open',
    },
  ],
  total: 2,
};

const mockInventory: PackageInventory = {
  items: [
    {
      id: 1,
      org: 'my-org',
      repo: 'my-org/repo1',
      name: 'web-app',
      package_type: 'docker',
      visibility: 'private',
      owner: 'dev-user',
      versions_count: 42,
      latest_version: 'v2.1.0',
      last_published_at: '2024-01-20T14:00:00Z',
      is_stale: false,
      published_outside_actions: false,
      published_by_external: false,
    },
    {
      id: 2,
      org: 'my-org',
      repo: null,
      name: '@my-org/shared-lib',
      package_type: 'npm',
      visibility: 'public',
      owner: 'external-user',
      versions_count: 5,
      latest_version: '1.0.3',
      last_published_at: '2023-06-01T00:00:00Z',
      is_stale: true,
      published_outside_actions: true,
      published_by_external: true,
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

const mockStaleImages: StaleImageList = {
  images: [
    {
      id: 11,
      org: 'my-org',
      repo: 'my-org/legacy',
      name: 'legacy-api',
      last_published_at: '2023-03-01T00:00:00Z',
      days_since_rebuild: 320,
      owner: 'dev-user',
    },
  ],
  total: 1,
  threshold_days: 90,
};

interface MockQueryReturn<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
}

let queryResults: Record<string, MockQueryReturn<unknown>>;

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: (opts: { queryKey: string[] }) => {
      const key = opts.queryKey.join('/');
      return (
        queryResults[key] ?? { data: undefined, isLoading: true, isError: false, refetch: vi.fn() }
      );
    },
  };
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PackagesPage />
    </QueryClientProvider>,
  );
}

function loadedResults(): Record<string, MockQueryReturn<unknown>> {
  return {
    'packages/summary': {
      data: mockSummary,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    },
    'packages/alerts': {
      data: mockAlerts,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    },
    'packages/inventory': {
      data: mockInventory,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    },
    'packages/stale-images': {
      data: mockStaleImages,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    },
  };
}

describe('PackagesPage', () => {
  beforeEach(() => {
    queryResults = {};
  });

  it('shows spinner while loading', () => {
    queryResults = {
      'packages/summary': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
      'packages/alerts': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
      'packages/inventory': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
      'packages/stale-images': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
    };
    const { container } = renderPage();
    expect(container.querySelector('.spinner')).not.toBeNull();
  });

  it('shows error banner on failure', () => {
    queryResults = {
      'packages/summary': {
        data: undefined,
        isLoading: false,
        isError: true,
        refetch: vi.fn(),
      },
      'packages/alerts': {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'packages/inventory': {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'packages/stale-images': {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText(/failed to load packages data/i)).toBeDefined();
  });

  it('renders metric cards with summary data', () => {
    queryResults = loadedResults();
    renderPage();
    expect(screen.getByText('25')).toBeDefined();
    expect(screen.getByText('Total Packages')).toBeDefined();
    expect(screen.getByText('Public Packages')).toBeDefined();
    expect(screen.getByText('Private Packages')).toBeDefined();
    expect(screen.getByText('Stale Images')).toBeDefined();
    expect(screen.getByText('Open Alerts')).toBeDefined();
  });

  it('renders overview tab by default with recent alerts', () => {
    queryResults = loadedResults();
    renderPage();
    expect(screen.getByText('Recent alerts')).toBeDefined();
    expect(screen.getAllByText(/my-public-pkg/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders packages by type in overview', () => {
    queryResults = loadedResults();
    renderPage();
    expect(screen.getByText('Packages by type')).toBeDefined();
  });

  it('switches to inventory tab', () => {
    queryResults = loadedResults();
    renderPage();
    fireEvent.click(screen.getByText('Inventory'));
    expect(screen.getByText('web-app')).toBeDefined();
    expect(screen.getByText('@my-org/shared-lib')).toBeDefined();
  });

  it('switches to alerts tab', () => {
    queryResults = loadedResults();
    renderPage();
    fireEvent.click(screen.getByText('Alerts'));
    expect(screen.getByText('public_exposure')).toBeDefined();
    expect(screen.getByText('stale_image')).toBeDefined();
  });

  it('switches to container health tab', () => {
    queryResults = loadedResults();
    renderPage();
    fireEvent.click(screen.getByText('Container Health'));
    expect(screen.getByText('legacy-api')).toBeDefined();
    expect(screen.getByText('320 days')).toBeDefined();
  });

  it('renders tabs with correct ARIA roles', () => {
    queryResults = loadedResults();
    renderPage();
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeDefined();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.length).toBe(4);
  });

  it('shows empty state when no alerts', () => {
    const emptyAlerts: PackageAlertList = { alerts: [], total: 0 };
    queryResults = {
      ...loadedResults(),
      'packages/alerts': {
        data: emptyAlerts,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText('No package security alerts.')).toBeDefined();
  });

  it('shows empty state when no inventory', () => {
    const emptyInv: PackageInventory = { items: [], total: 0, page: 1, page_size: 50 };
    queryResults = {
      ...loadedResults(),
      'packages/inventory': {
        data: emptyInv,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    fireEvent.click(screen.getByText('Inventory'));
    expect(screen.getByText('No packages found.')).toBeDefined();
  });

  it('shows all container images up to date when no stale images', () => {
    const emptyStale: StaleImageList = { images: [], total: 0, threshold_days: 90 };
    queryResults = {
      ...loadedResults(),
      'packages/stale-images': {
        data: emptyStale,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    fireEvent.click(screen.getByText('Container Health'));
    expect(screen.getByText('All container images are up to date.')).toBeDefined();
  });

  it('displays visibility badges in inventory', () => {
    queryResults = loadedResults();
    renderPage();
    fireEvent.click(screen.getByText('Inventory'));
    // Both public and private visibility badges should be present
    expect(screen.getByText('private')).toBeDefined();
    expect(screen.getByText('public')).toBeDefined();
  });

  it('displays flag icons for flagged packages in inventory', () => {
    queryResults = loadedResults();
    renderPage();
    fireEvent.click(screen.getByText('Inventory'));
    // The second package has all flags set
    expect(screen.getByText('⏰')).toBeDefined();
    expect(screen.getByText('⚠️')).toBeDefined();
    expect(screen.getByText('🔓')).toBeDefined();
  });
});
