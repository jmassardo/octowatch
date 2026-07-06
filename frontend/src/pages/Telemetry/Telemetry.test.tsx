import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TelemetryPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

vi.mock('../../api/telemetry', () => ({
  getTelemetrySummary: vi.fn(),
  getStreamStatus: vi.fn(),
  getWorkerHealth: vi.fn(),
  getEventVolume: vi.fn(),
  getIngestionErrors: vi.fn(),
}));

import * as telemetryApi from '../../api/telemetry';

function renderPage(route = '/monitoring/telemetry/streams') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route
          path="/monitoring/telemetry/:tab"
          element={
            <QueryClientProvider client={qc}>
              <TelemetryPage />
            </QueryClientProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('TelemetryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(telemetryApi.getTelemetrySummary).mockResolvedValue({
      events_per_second: 12,
      events_today: 1234,
      active_workers: 4,
      queue_depth: 9,
      last_event_at: '2024-01-01T00:00:00Z',
      error_rate: 1.2,
    });
    vi.mocked(telemetryApi.getStreamStatus).mockResolvedValue({ streams: [] });
    vi.mocked(telemetryApi.getWorkerHealth).mockResolvedValue({
      active_workers: [],
      health_events: [],
    });
    vi.mocked(telemetryApi.getEventVolume).mockResolvedValue({
      volume: [],
      top_actions: [],
    });
    vi.mocked(telemetryApi.getIngestionErrors).mockResolvedValue({
      errors: [],
      gaps: [],
    });
  });

  it('renders page header', () => {
    renderPage();
    expect(screen.getByText('Ingestion Telemetry')).toBeInTheDocument();
  });

  it('renders metric cards when data loads', async () => {
    vi.mocked(telemetryApi.getTelemetrySummary).mockResolvedValue({
      events_per_second: 42,
      events_today: 2500,
      active_workers: 8,
      queue_depth: 16,
      last_event_at: '2024-01-01T00:00:00Z',
      error_rate: 2.5,
    });

    renderPage();

    expect(await screen.findByText('42')).toBeInTheDocument();
    expect(await screen.findByText('2,500')).toBeInTheDocument();
    expect(await screen.findByText('8')).toBeInTheDocument();
    expect(await screen.findByText('16')).toBeInTheDocument();
    expect(await screen.findByText('2.5%')).toBeInTheDocument();
  });

  it('renders tab buttons', () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'Stream Status' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Worker Health' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Event Volume' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Errors & Gaps' })).toBeInTheDocument();
  });

  it('switches tabs on click', () => {
    renderPage();
    const workerTab = screen.getByRole('button', { name: 'Worker Health' });

    fireEvent.click(workerTab);

    expect(workerTab.className).toContain('tabActive');
  });

  it('shows spinner while loading', () => {
    vi.mocked(telemetryApi.getTelemetrySummary).mockReturnValue(new Promise(() => {}));

    renderPage();

    const spinner = document.querySelector('[class*="spinner"]');
    expect(spinner).not.toBeNull();
  });

  it('shows error banner on failure', async () => {
    vi.mocked(telemetryApi.getTelemetrySummary).mockRejectedValue(new Error('Network error'));

    renderPage();

    expect(await screen.findByText('Failed to load telemetry')).toBeInTheDocument();
  });
});
