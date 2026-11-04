import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { DeliveryTimelinePane } from './DeliveryTimelinePane';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

const mockGetDeliveryTimeline = vi.fn();

vi.mock('../../api/deliveryTimeline', () => ({
  getDeliveryTimeline: (...args: unknown[]) => mockGetDeliveryTimeline(...args),
}));

describe('DeliveryTimelinePane', () => {
  beforeEach(() => {
    mockGetDeliveryTimeline.mockReset();
    mockGetDeliveryTimeline.mockResolvedValue({
      total_prs: 42,
      avg_backlog_hours: 4.5,
      avg_dev_hours: 12.3,
      avg_review_hours: 8.1,
      avg_deploy_hours: 22.7,
      avg_total_hours: 47.6,
      median_total_hours: 40.2,
      p95_total_hours: 90.1,
      bottleneck_phase: 'deploy',
      timelines: [
        {
          id: '1',
          pr_number: 101,
          repo: 'octowatch',
          org: 'octodemo',
          issue_numbers: [5],
          backlog_hours: 3,
          dev_hours: 10,
          review_hours: 6,
          deploy_hours: 20,
          total_hours: 39,
          pr_merged_at: '2026-06-01T00:00:00Z',
          created_at: '2026-05-30T00:00:00Z',
        },
        {
          id: '2',
          pr_number: 102,
          repo: 'octowatch',
          org: 'octodemo',
          issue_numbers: [6],
          backlog_hours: 6,
          dev_hours: 15,
          review_hours: 10,
          deploy_hours: 25,
          total_hours: 56,
          pr_merged_at: '2026-06-03T00:00:00Z',
          created_at: '2026-06-01T00:00:00Z',
        },
      ],
    });
  });

  it('renders summary metric cards', async () => {
    renderWithProviders(<DeliveryTimelinePane />);
    expect(await screen.findByText('Total PRs')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Avg Total')).toBeInTheDocument();
  });

  it('surfaces the bottleneck phase callout', async () => {
    renderWithProviders(<DeliveryTimelinePane />);
    expect(await screen.findByText('Bottleneck phase: Deploy')).toBeInTheDocument();
  });

  it('renders the phase breakdown chart', async () => {
    renderWithProviders(<DeliveryTimelinePane />);
    expect(await screen.findByText('Phase breakdown — average hours')).toBeInTheDocument();
  });

  it('renders the delivery time trend chart', async () => {
    renderWithProviders(<DeliveryTimelinePane />);
    expect(await screen.findByText('Total delivery time trend')).toBeInTheDocument();
  });

  it('shows an error banner when the request fails', async () => {
    mockGetDeliveryTimeline.mockReset();
    mockGetDeliveryTimeline.mockRejectedValue(new Error('boom'));
    renderWithProviders(<DeliveryTimelinePane />);
    expect(await screen.findByText('Failed to load delivery timeline metrics')).toBeInTheDocument();
  });
});
