import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ActorsPage } from './index';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ login: 'alice' }) };
});

const mockGetActorProfile = vi.fn().mockResolvedValue({
  login: 'alice',
  avatar_url: 'https://github.com/alice.png',
  display_name: 'Alice Smith',
  roles: ['analyst'],
  org_memberships: ['acme'],
  detection_count: 3,
  event_count: 150,
  risk_score: 42,
  risk_level: 'medium',
  first_seen: '2024-06-01T00:00:00Z',
  last_seen: '2025-01-15T00:00:00Z',
});

const mockGetActorEvents = vi.fn().mockResolvedValue({
  items: [
    {
      id: 1,
      created_at: '2025-01-15T10:00:00Z',
      action: 'repo.create',
      namespace: 'acme',
      org: 'acme',
      repo: 'acme/web',
      source_ip: '1.2.3.4',
      geo_country_code: 'US',
      geo_city: 'NYC',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  has_next: false,
});

const mockGetActorDetections = vi.fn().mockResolvedValue({
  items: [
    {
      id: 10,
      title: 'Suspicious login',
      severity: 'high',
      status: 'open',
      triggered_at: '2025-01-10T08:00:00Z',
      rule_name: 'impossible_travel',
      org: 'acme',
      repo: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  has_next: false,
});

const mockGetActorLocations = vi.fn().mockResolvedValue({
  locations: [
    {
      country_code: 'US',
      city: 'New York',
      latitude: 40.7,
      longitude: -74.0,
      event_count: 50,
      last_seen: '2025-01-15T10:00:00Z',
    },
  ],
  total_events: 50,
});

vi.mock('../../api/actors', () => ({
  getActorProfile: (...args: unknown[]) => mockGetActorProfile(...args),
  getActorEvents: (...args: unknown[]) => mockGetActorEvents(...args),
  getActorDetections: (...args: unknown[]) => mockGetActorDetections(...args),
  getActorLocations: (...args: unknown[]) => mockGetActorLocations(...args),
}));

vi.mock('../../components/charts/GeoMap', () => ({
  GeoMap: () => <div data-testid="geo-map" />,
}));

describe('ActorsPage', () => {
  it('renders actor profile header', async () => {
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      expect(screen.getByText('@alice')).toBeInTheDocument();
    });

    expect(screen.getByText('150 events')).toBeInTheDocument();
    expect(screen.getByText('3 detections')).toBeInTheDocument();
  });

  it('shows risk score', async () => {
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument();
      expect(screen.getByText('medium')).toBeInTheDocument();
    });
  });

  it('renders activity tab by default', async () => {
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      expect(screen.getByText('repo.create')).toBeInTheDocument();
    });

    expect(screen.getByText('acme/web')).toBeInTheDocument();
  });

  it('switches to detections tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      expect(screen.getByText('@alice')).toBeInTheDocument();
    });

    await user.click(screen.getByText('🛡️ Detections'));

    await waitFor(() => {
      expect(screen.getByText('Suspicious login')).toBeInTheDocument();
    });
  });

  it('switches to geo tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      expect(screen.getByText('@alice')).toBeInTheDocument();
    });

    await user.click(screen.getByText('🌍 Locations'));

    await waitFor(() => {
      expect(screen.getByText('New York')).toBeInTheDocument();
      expect(screen.getByTestId('geo-map')).toBeInTheDocument();
    });
  });

  it('shows avatar with GitHub URL', async () => {
    renderWithProviders(<ActorsPage />);

    await waitFor(() => {
      const img = screen.getByAltText('alice');
      expect(img).toHaveAttribute('src', 'https://github.com/alice.png?size=80');
    });
  });
});
