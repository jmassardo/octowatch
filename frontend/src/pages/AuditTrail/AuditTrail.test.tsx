import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { AuditTrailPage } from './index';

const mockListAuditLog = vi.fn();
const mockExportAuditLogCsv = vi.fn();
const mockHasPermission = vi.fn();

vi.mock('../../api/auditLog', () => ({
  listAuditLog: (...args: unknown[]) => mockListAuditLog(...args),
  exportAuditLogCsv: (...args: unknown[]) => mockExportAuditLogCsv(...args),
}));

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: [],
    roles: [],
    isLoading: false,
    hasPermission: (...args: unknown[]) => mockHasPermission(...args),
    hasAnyPermission: () => true,
    hasRole: () => false,
    scopedOrgs: [],
    scopedRepos: [],
    scopeType: 'global',
    isOrgInScope: () => true,
    isRepoInScope: () => true,
    canEdit: () => false,
  }),
}));

const defaultResponse = {
  items: [
    {
      id: 1,
      timestamp: '2026-06-15T12:30:00Z',
      actor: 'octocat',
      action: 'settings.update',
      resource_type: 'settings',
      resource_id: 'retention',
      details: { key: 'retention_days', value: 365 },
      ip_address: '127.0.0.1',
      user_agent: 'test',
      outcome: 'success',
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
  has_more: false,
};

describe('AuditTrailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasPermission.mockImplementation((resource: string, action: string) => {
      if (resource !== 'audit_log') return false;
      return action === 'view' || action === 'export';
    });
    mockListAuditLog.mockResolvedValue(defaultResponse);
  });

  it('renders the page header', () => {
    renderWithProviders(<AuditTrailPage />);
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
  });

  it('renders audit rows from API', async () => {
    renderWithProviders(<AuditTrailPage />);

    expect(await screen.findByText('octocat')).toBeInTheDocument();
    expect(screen.getByText('settings.update')).toBeInTheDocument();
    expect(screen.getAllByText('success').length).toBeGreaterThan(0);
  });

  it('applies filters when clicking Apply Filters', async () => {
    const user = userEvent.setup();
    renderWithProviders(<AuditTrailPage />);

    await screen.findByText('octocat');
    await user.type(screen.getByPlaceholderText('e.g. octocat'), 'alice');
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }));

    await waitFor(() => {
      expect(mockListAuditLog).toHaveBeenLastCalledWith(
        expect.objectContaining({
          actor: 'alice',
        }),
      );
    });
  });

  it('exports CSV with active filters', async () => {
    const user = userEvent.setup();
    renderWithProviders(<AuditTrailPage />);

    await screen.findByText('octocat');
    await user.type(screen.getByPlaceholderText('e.g. octocat'), 'alice');
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }));
    await user.click(screen.getByRole('button', { name: 'Export CSV' }));

    expect(mockExportAuditLogCsv).toHaveBeenCalledWith(
      expect.objectContaining({
        actor: 'alice',
      }),
    );
  });

  it('shows empty state when no rows returned', async () => {
    mockListAuditLog.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
      has_more: false,
    });

    renderWithProviders(<AuditTrailPage />);

    expect(
      await screen.findByText('No audit events found for current filters.'),
    ).toBeInTheDocument();
  });
});
