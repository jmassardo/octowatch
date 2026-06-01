import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { RulesPage } from './index';
import * as rulesApi from '../../api/rules';
import type { RuleListResponse } from '../../types/detections';

vi.mock('../../api/rules', () => ({
  listRules: vi.fn(),
  getRule: vi.fn(),
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

const rulesResponse: RuleListResponse = {
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
};

describe('RulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(rulesApi.listRules).mockResolvedValue(rulesResponse);
    vi.mocked(rulesApi.getRule).mockImplementation(async (id) => {
      const rule = rulesResponse.items.find((item) => item.id === id);
      if (!rule) {
        throw new Error('not found');
      }
      return rule;
    });
  });

  function renderPage() {
    return renderWithProviders(<RulesPage />, { route: '/rules', routePath: '/rules/:ruleId?' });
  }

  it('renders page title and subtitle', async () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: /detection rules/i })).toBeInTheDocument();
    expect(screen.getByText(/configure automated threat detection patterns/i)).toBeInTheDocument();
  });

  it('renders rule table with updated headers', async () => {
    renderPage();

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
    ]);
  });

  it('passes server-side filters to listRules', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Impossible Travel Login');
    await user.selectOptions(screen.getByLabelText(/filter by severity/i), 'high');
    await user.selectOptions(screen.getByLabelText(/filter by logic type/i), 'statistical');
    await user.selectOptions(screen.getByLabelText(/filter by mode/i), 'active');
    await user.type(screen.getByLabelText(/search rules/i), 'travel');

    expect(vi.mocked(rulesApi.listRules)).toHaveBeenLastCalledWith(
      expect.objectContaining({
        severity: 'high',
        logic_type: 'statistical',
        mode: 'active',
        search: 'travel',
        sort: 'created_at',
        order: 'desc',
      }),
    );
  });

  it('opens a rule detail drawer on row click', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('Impossible Travel Login'));

    expect(await screen.findByText(/rule detail: impossible travel login/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /version history/i })).toBeInTheDocument();
    expect(
      screen.getByText(/detect logins from geographically impossible locations/i),
    ).toBeInTheDocument();
  });

  it('opens version history from the version link', async () => {
    const user = userEvent.setup();
    renderPage();

    const versionLink = await screen.findByText('v2.0.0');
    await user.click(versionLink);

    expect(await screen.findByText('Version history')).toBeInTheDocument();
  });

  it('renders a single new rule button and opens the wizard', async () => {
    const user = userEvent.setup();
    renderPage();

    const buttons = screen.getAllByRole('button', { name: /^new rule$/i });
    expect(buttons).toHaveLength(1);

    await user.click(buttons[0]!);
    expect(await screen.findByText('Wizard Content')).toBeInTheDocument();
  });

  it('shows bulk actions when rules are selected', async () => {
    const user = userEvent.setup();
    renderPage();

    const checkbox = await screen.findByRole('checkbox', {
      name: /select impossible travel login/i,
    });
    await user.click(checkbox);

    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /set monitoring/i })).toBeInTheDocument();
  });

  it('opens analytics from the detail drawer', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('Impossible Travel Login'));
    await user.click(await screen.findByRole('button', { name: /analytics/i }));

    expect(await screen.findByText(/analytics: impossible travel login/i)).toBeInTheDocument();
    expect(screen.getByText('Analytics Content')).toBeInTheDocument();
  });

  it('deep links to a specific rule detail via URL param', async () => {
    renderWithProviders(<RulesPage />, { route: '/rules/1', routePath: '/rules/:ruleId' });

    expect(await screen.findByText(/rule detail: impossible travel login/i)).toBeInTheDocument();
  });

  it('deep links to version history via URL param and view query', async () => {
    renderWithProviders(<RulesPage />, {
      route: '/rules/1?view=versions',
      routePath: '/rules/:ruleId',
    });

    expect(await screen.findByText('Version history')).toBeInTheDocument();
  });

  it('deep links to analytics via URL param and view query', async () => {
    renderWithProviders(<RulesPage />, {
      route: '/rules/2?view=analytics',
      routePath: '/rules/:ruleId',
    });

    expect(await screen.findByText(/analytics: secret leakage detection/i)).toBeInTheDocument();
    expect(screen.getByText('Analytics Content')).toBeInTheDocument();
  });
});
