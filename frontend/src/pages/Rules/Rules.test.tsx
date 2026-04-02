import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { RulesPage } from './index';

vi.mock('../../api/rules', () => ({
  listRules: vi.fn().mockResolvedValue({
    items: [
      {
        id: 1,
        name: 'Impossible Travel Login',
        slug: 'impossible-travel',
        description: 'Detect logins from geographically impossible locations',
        category: 'impossible_travel',
        default_severity: 'high',
        default_confidence: 'high',
        logic_type: 'statistical',
        logic_config: {},
        enabled: true,
        status: 'active',
        version: 2,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-06-15T10:30:00Z',
      },
      {
        id: 2,
        name: 'Secret Leakage Detection',
        slug: 'secret-leakage',
        description: null,
        category: 'secret_leakage',
        default_severity: 'critical',
        default_confidence: 'medium',
        logic_type: 'pattern',
        logic_config: {},
        enabled: true,
        status: 'active',
        version: 1,
        created_at: '2024-02-01T00:00:00Z',
        updated_at: '2024-05-20T14:00:00Z',
      },
      {
        id: 3,
        name: 'Draft Rule',
        slug: 'draft-rule',
        description: null,
        category: 'other',
        default_severity: 'low',
        default_confidence: 'low',
        logic_type: 'threshold',
        logic_config: {},
        enabled: false,
        status: 'draft',
        version: 1,
        created_at: '2024-03-01T00:00:00Z',
        updated_at: null,
      },
    ],
    total: 3,
    page: 1,
    page_size: 50,
  }),
  createRule: vi.fn().mockResolvedValue({}),
  updateRule: vi.fn().mockResolvedValue({}),
  deleteRule: vi.fn().mockResolvedValue(undefined),
  listRuleVersions: vi.fn().mockResolvedValue([]),
  validateRuleConfig: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
}));

describe('RulesPage', () => {
  it('renders page title and subtitle', async () => {
    renderWithProviders(<RulesPage />);

    expect(screen.getByRole('heading', { level: 1, name: /detection rules/i })).toBeInTheDocument();
    expect(screen.getByText(/manage built-in and custom detection rules/i)).toBeInTheDocument();
  });

  it('renders rule table with correct headers', async () => {
    renderWithProviders(<RulesPage />);

    const table = await screen.findByRole('table');
    // Get only the first row of column headers (skip filter row)
    const headerRow = within(table).getAllByRole('row')[0];
    const headers = within(headerRow).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent?.replace(/[⇅↑↓]/g, '').trim());

    expect(headerTexts).toEqual(['Status', 'Rule name', 'Logic', 'Severity', 'Detections (30d)', 'Version', '']);
  });

  it('renders all 3 rules with names', async () => {
    renderWithProviders(<RulesPage />);

    expect(await screen.findByText('Impossible Travel Login')).toBeInTheDocument();
    expect(screen.getByText('Secret Leakage Detection')).toBeInTheDocument();
    expect(screen.getByText('Draft Rule')).toBeInTheDocument();
  });

  it('shows 0 for active rule detections and — for draft', async () => {
    renderWithProviders(<RulesPage />);

    await screen.findByText('Impossible Travel Login');

    const table = screen.getByRole('table');
    const rows = within(table).getAllByRole('row');
    // rows[0] is header; rows[1] is filter row; rows[2..4] are data rows
    const dataRows = rows.filter((r) => within(r).queryAllByRole('cell').length > 0);

    const activeRow1Cells = within(dataRows[0]).getAllByRole('cell');
    expect(activeRow1Cells[4].textContent).toBe('0');

    const activeRow2Cells = within(dataRows[1]).getAllByRole('cell');
    expect(activeRow2Cells[4].textContent).toBe('0');

    const draftRowCells = within(dataRows[2]).getAllByRole('cell');
    expect(draftRowCells[4].textContent).toBe('—');
  });

  it('version numbers are clickable with clickableVersion class', async () => {
    renderWithProviders(<RulesPage />);

    await screen.findByText('Impossible Travel Login');

    const versions = document.querySelectorAll('.clickableVersion');
    expect(versions).toHaveLength(3);

    expect(screen.getByText('v2.0.0')).toBeInTheDocument();
    expect(screen.getAllByText('v1.0.0')).toHaveLength(2);
  });

  it('clicking version opens modal with rule details', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RulesPage />);

    const versionLink = await screen.findByText('v2.0.0');
    await user.click(versionLink);

    expect(await screen.findByText('Version history')).toBeInTheDocument();
  });

  it('version modal shows rule name, version number, and status', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RulesPage />);

    const versionLink = await screen.findByText('v2.0.0');
    await user.click(versionLink);

    const modalTitle = await screen.findByText('Version history');
    const modal = modalTitle.closest('.dialog')!;

    expect(within(modal as HTMLElement).getByText('Rule name')).toBeInTheDocument();
    expect(within(modal as HTMLElement).getByText('Current version')).toBeInTheDocument();
    expect(within(modal as HTMLElement).getByText('v2.0.0')).toBeInTheDocument();
  });

  it('new rule button exists', () => {
    renderWithProviders(<RulesPage />);

    expect(screen.getByRole('button', { name: /new rule/i })).toBeInTheDocument();
  });

  it('sync from GitHub button exists', () => {
    renderWithProviders(<RulesPage />);

    expect(screen.getByRole('button', { name: /sync from github/i })).toBeInTheDocument();
  });
});
