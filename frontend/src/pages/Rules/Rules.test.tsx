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
        mode: 'active',
        status: 'active',
        version: 2,
        git_commit_sha: null,
        created_by: 'admin',
        updated_by: null,
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
        mode: 'monitoring',
        status: 'active',
        version: 1,
        git_commit_sha: null,
        created_by: 'admin',
        updated_by: null,
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
        mode: 'disabled',
        status: 'draft',
        version: 1,
        git_commit_sha: null,
        created_by: 'admin',
        updated_by: null,
        created_at: '2024-03-01T00:00:00Z',
        updated_at: '2024-03-01T00:00:00Z',
      },
    ],
    total: 3,
    limit: 25,
    offset: 0,
  }),
  createRule: vi.fn().mockResolvedValue({}),
  updateRule: vi.fn().mockResolvedValue({}),
  deleteRule: vi.fn().mockResolvedValue(undefined),
  listRuleVersions: vi.fn().mockResolvedValue([]),
  validateRuleConfig: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
  bulkUpdateRules: vi.fn().mockResolvedValue({ updated: 1, failed: [] }),
}));

vi.mock('./RuleAnalytics', () => ({
  RuleAnalytics: () => <div>Analytics Content</div>,
}));

vi.mock('./BacktestPanel', () => ({
  BacktestPanel: () => <div>Backtest Content</div>,
}));

vi.mock('./RuleWizard', () => ({
  RuleWizard: () => <div>Wizard Content</div>,
}));

describe('RulesPage', () => {
  it('renders page title and subtitle', async () => {
    renderWithProviders(<RulesPage />);

    expect(screen.getByRole('heading', { level: 1, name: /detection rules/i })).toBeInTheDocument();
    expect(screen.getByText(/configure automated threat detection patterns/i)).toBeInTheDocument();
  });

  it('renders rule table with correct headers', async () => {
    renderWithProviders(<RulesPage />);

    const table = await screen.findByRole('table');
    const headerRow = within(table).getAllByRole('row')[0];
    const headers = within(headerRow).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent?.replace(/[⇅↑↓ⓘ]/g, '').trim());

    expect(headerTexts).toEqual([
      '',
      'Status',
      'Mode',
      'Rule name',
      'Logic',
      'Severity',
      'Detections (30d)',
      'Version',
      '',
    ]);
  });

  it('renders all rules with names', async () => {
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
    const dataRows = rows.filter((r) => within(r).queryAllByRole('cell').length > 0);

    const activeRow1Cells = within(dataRows[0]).getAllByRole('cell');
    expect(activeRow1Cells[6].textContent).toBe('0');

    const activeRow2Cells = within(dataRows[1]).getAllByRole('cell');
    expect(activeRow2Cells[6].textContent).toBe('0');

    const draftRowCells = within(dataRows[2]).getAllByRole('cell');
    expect(draftRowCells[6].textContent).toBe('—');
  });

  it('shows mode badges', async () => {
    renderWithProviders(<RulesPage />);

    expect(await screen.findByText('monitoring')).toBeInTheDocument();
    expect(screen.getByText('disabled')).toBeInTheDocument();
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

  it('renders new rule buttons', () => {
    renderWithProviders(<RulesPage />);

    expect(screen.getByRole('button', { name: /^new rule$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new rule \(wizard\)/i })).toBeInTheDocument();
  });

  it('shows bulk actions when rules are selected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RulesPage />);

    const checkbox = await screen.findByRole('checkbox', {
      name: /select impossible travel login/i,
    });
    await user.click(checkbox);

    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /set monitoring/i })).toBeInTheDocument();
  });

  it('opens analytics drawer from row actions', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RulesPage />);

    const analyticsButtons = await screen.findAllByRole('button', { name: /analytics/i });
    await user.click(analyticsButtons[0]!);

    expect(await screen.findByText(/analytics: impossible travel login/i)).toBeInTheDocument();
    expect(screen.getByText('Analytics Content')).toBeInTheDocument();
  });
});
