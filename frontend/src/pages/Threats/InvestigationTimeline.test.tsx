import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { InvestigationTimeline } from './InvestigationTimeline';

const mockGetDetectionTimeline = vi.fn().mockResolvedValue({
  detection_id: 1,
  detection_title: 'Suspicious token creation',
  detection_severity: 'high',
  detection_category: null,
  events: [
    {
      id: 101,
      created_at: '2025-01-15T10:00:00Z',
      action: 'oauth_application.create',
      actor: 'alice',
      org: 'acme',
      repo: null,
      source_ip: '1.2.3.4',
      geo_city: 'New York',
      geo_country_code: 'US',
      geo_latitude: 40.7,
      geo_longitude: -74.0,
      is_sequence_step: false,
      sequence_index: null,
      data: {},
    },
    {
      id: 102,
      created_at: '2025-01-15T10:05:00Z',
      action: 'oauth_application.access',
      actor: 'alice',
      org: 'acme',
      repo: 'acme/web',
      source_ip: '1.2.3.4',
      geo_city: 'New York',
      geo_country_code: 'US',
      geo_latitude: 40.7,
      geo_longitude: -74.0,
      is_sequence_step: true,
      sequence_index: 0,
      data: {},
    },
  ],
  sequence_steps: ['Step 1'],
  context_data: {},
});

vi.mock('../../api/executive', () => ({
  getDetectionTimeline: (...args: unknown[]) => mockGetDetectionTimeline(...args),
}));

vi.mock('../../api/events', () => ({
  getRawEvent: vi.fn().mockResolvedValue({ id: 101, action: 'test' }),
}));

vi.mock('../../components/charts/GeoMap', () => ({
  GeoMap: () => <div data-testid="geo-map" />,
}));

describe('InvestigationTimeline', () => {
  const onClose = vi.fn();

  it('renders timeline events', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByText('Investigation Timeline')).toBeInTheDocument();
    });

    expect(screen.getByText('oauth_application.create')).toBeInTheDocument();
    expect(screen.getByText('oauth_application.access')).toBeInTheDocument();
  });

  it('shows detection title and severity', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByText('Suspicious token creation')).toBeInTheDocument();
      expect(screen.getByText('high')).toBeInTheDocument();
    });
  });

  it('marks sequence steps', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByText('Step 1')).toBeInTheDocument();
    });
  });

  it('shows actor links', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      const actorLinks = screen.getAllByText('@alice');
      expect(actorLinks.length).toBeGreaterThan(0);
    });
  });

  it('shows geo info', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      const geoElements = screen.getAllByText(/New York, US/);
      expect(geoElements.length).toBeGreaterThan(0);
    });
  });

  it('shows empty state for no events', async () => {
    mockGetDetectionTimeline.mockResolvedValueOnce({
      detection_id: 2,
      detection_title: 'Empty detection',
      detection_severity: 'low',
      detection_category: null,
      events: [],
      sequence_steps: [],
      context_data: {},
    });

    renderWithProviders(
      <InvestigationTimeline detectionId={2} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByText('No events found for this detection')).toBeInTheDocument();
    });
  });

  it('calls onClose when close button clicked', async () => {
    renderWithProviders(
      <InvestigationTimeline detectionId={1} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByText('Investigation Timeline')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByLabelText('Close timeline'));
    expect(onClose).toHaveBeenCalled();
  });
});
