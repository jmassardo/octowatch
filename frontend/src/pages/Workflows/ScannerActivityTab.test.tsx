import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ScannerActivityTab } from './ScannerActivityTab';

import * as workflowScannerApi from '../../api/workflowScanner';

vi.mock('../../api/workflowScanner');

const mockedListScanActivity = vi.mocked(workflowScannerApi.listScanActivity);

function renderWithProviders(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ScannerActivityTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when no activity', async () => {
    mockedListScanActivity.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('No scanner activity yet')).toBeInTheDocument();
  });

  it('renders activity table with data', async () => {
    mockedListScanActivity.mockResolvedValue({
      items: [
        {
          id: 1,
          trigger_event_ids: [10, 11],
          org: 'my-org',
          repo: 'my-repo',
          workflow_path: '.github/workflows/ci.yml',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:01Z',
          status: 'completed' as const,
          checks_performed: ['self-hosted-runner'],
          findings_count: 2,
          data_sources: ['audit_log'],
          duration_ms: 150,
        },
      ],
      total: 1,
    });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('my-org/my-repo')).toBeInTheDocument();
  });

  it('renders status badges correctly', async () => {
    mockedListScanActivity.mockResolvedValue({
      items: [
        {
          id: 1,
          trigger_event_ids: [],
          org: 'org',
          repo: 'repo',
          workflow_path: '.github/workflows/x.yml',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: null,
          status: 'running' as const,
          checks_performed: [],
          findings_count: 0,
          data_sources: ['audit_log'],
          duration_ms: null,
        },
      ],
      total: 1,
    });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('running')).toBeInTheDocument();
  });

  it('renders data source chips', async () => {
    mockedListScanActivity.mockResolvedValue({
      items: [
        {
          id: 1,
          trigger_event_ids: [5],
          org: 'org',
          repo: 'repo',
          workflow_path: '.github/workflows/deploy.yml',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:02Z',
          status: 'completed' as const,
          checks_performed: ['pat-triggered-workflow'],
          findings_count: 1,
          data_sources: ['audit_log'],
          duration_ms: 200,
        },
      ],
      total: 1,
    });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('Audit Log')).toBeInTheDocument();
  });

  it('renders event-driven trigger badge', async () => {
    mockedListScanActivity.mockResolvedValue({
      items: [
        {
          id: 1,
          trigger_event_ids: [1, 2, 3],
          org: 'org',
          repo: 'repo',
          workflow_path: '.github/workflows/ci.yml',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:01Z',
          status: 'completed' as const,
          checks_performed: [],
          findings_count: 0,
          data_sources: ['audit_log'],
          duration_ms: 100,
        },
      ],
      total: 1,
    });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('Event-driven')).toBeInTheDocument();
  });

  it('renders manual trigger badge when no event IDs', async () => {
    mockedListScanActivity.mockResolvedValue({
      items: [
        {
          id: 2,
          trigger_event_ids: [],
          org: 'org',
          repo: 'repo',
          workflow_path: '.github/workflows/ci.yml',
          started_at: '2026-01-01T00:00:00Z',
          completed_at: '2026-01-01T00:00:01Z',
          status: 'completed' as const,
          checks_performed: [],
          findings_count: 0,
          data_sources: ['audit_log'],
          duration_ms: 100,
        },
      ],
      total: 1,
    });
    renderWithProviders(<ScannerActivityTab />);
    expect(await screen.findByText('Manual')).toBeInTheDocument();
  });
});
