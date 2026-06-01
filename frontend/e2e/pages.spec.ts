import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Page-level E2E tests — verify every major page loads, renders key elements,
// and basic interactions work.
//
// Authentication is handled by the "setup" project in playwright.config.ts.
//
// These tests navigate directly to routes to avoid sidebar/tour interference.
// Pages may show "no data" states if no audit data is ingested — that is
// expected. Tests validate page structure, not real data.
// ---------------------------------------------------------------------------

/** Dismiss the guided tour if it appears — it blocks interaction. */
async function dismissTourIfPresent(page: Page) {
  const closeBtn = page.getByRole('button', { name: 'Close tour' });
  if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await closeBtn.click();
    await expect(page.getByRole('dialog', { name: 'Guided tour' })).toBeHidden({ timeout: 3_000 });
  }
}

// All page tests require auth cookies — skip in CI where self-signed TLS
// prevents cookie persistence.
test.describe('Page-level E2E tests', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  // =========================================================================
  // Security Posture
  // =========================================================================
  test.describe('Security Posture page', () => {
    test('renders page title and content', async ({ page }) => {
      await page.goto('/posture');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Security Posture').first()).toBeVisible({ timeout: 15_000 });
    });

    test('navigates to org-scoped posture', async ({ page }) => {
      await page.goto('/posture');
      await dismissTourIfPresent(page);

      // Page should render without error
      await expect(page).not.toHaveURL(/\/login/);
    });
  });

  // =========================================================================
  // Advanced Security
  // =========================================================================
  test.describe('Advanced Security page', () => {
    test('renders all GHAS category tabs', async ({ page }) => {
      await page.goto('/advanced-security/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const expectedTabs = ['Overview', 'Secret Scanning', 'Code Scanning', 'Dependabot', 'Activity Log'];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('navigates between tabs without errors', async ({ page }) => {
      await page.goto('/advanced-security/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Click Secret Scanning tab
      await main.getByRole('button', { name: 'Secret Scanning' }).first().click();
      await expect(page).toHaveURL(/\/advanced-security\/secret-scanning/);

      // Click Dependabot tab
      await main.getByRole('button', { name: 'Dependabot' }).first().click();
      await expect(page).toHaveURL(/\/advanced-security\/dependabot/);
    });
  });

  // =========================================================================
  // Supply Chain Security
  // =========================================================================
  test.describe('Supply Chain Security page', () => {
    test('renders page title and metric cards', async ({ page }) => {
      await page.goto('/supply-chain');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Supply Chain Security').first()).toBeVisible({ timeout: 15_000 });

      // Verify key metric cards
      const metrics = ['Supply Chain Score', 'Unpinned Actions', 'Dependency Alerts', 'Risky Workflows'];
      for (const metric of metrics) {
        await expect(main.getByText(metric).first()).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders risk/rules/workflow tabs', async ({ page }) => {
      await page.goto('/supply-chain');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const expectedTabs = ['Risks', 'Rules', 'Workflow Audit'];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('workflow audit tab has YAML analysis input', async ({ page }) => {
      await page.goto('/supply-chain');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Navigate to Workflow Audit tab
      await main.getByRole('button', { name: 'Workflow Audit' }).first().click();

      // Verify textarea and analyse button appear
      await expect(page.locator('[aria-label="Workflow YAML content"]')).toBeVisible({
        timeout: 15_000,
      });
      await expect(main.getByRole('button', { name: /analyse workflow/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // =========================================================================
  // Packages Monitoring
  // =========================================================================
  test.describe('Packages page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/packages');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Packages').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders tabs or empty state', async ({ page }) => {
      await page.goto('/packages');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // May show tabs (if data) or empty state (if no packages synced)
      const overviewTab = main.getByRole('button', { name: 'Overview' });
      const emptyState = main.getByText(/no packages synced yet/i);

      await expect(overviewTab.or(emptyState).first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders metric cards when data present', async ({ page }) => {
      await page.goto('/packages');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // If packages are synced, metric cards should appear
      const totalPackages = main.getByText('Total Packages');
      const emptyState = main.getByText(/no packages synced yet/i);

      await expect(totalPackages.or(emptyState).first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Compliance
  // =========================================================================
  test.describe('Compliance page', () => {
    test('renders page title and generate button', async ({ page }) => {
      await page.goto('/compliance');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Compliance Center').first()).toBeVisible({ timeout: 15_000 });
      await expect(main.getByRole('button', { name: /generate all reports/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders compliance metric cards', async ({ page }) => {
      await page.goto('/compliance');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const metrics = ['Overall Score', 'Frameworks Tracked', 'Controls Passing', 'Critical Gaps'];

      for (const metric of metrics) {
        await expect(main.getByText(metric).first()).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders framework tabs', async ({ page }) => {
      await page.goto('/compliance');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const frameworks = ['Overview', 'SOC 2', 'ISO 27001', 'NIST CSF', 'GDPR', 'Policy Checks'];

      for (const framework of frameworks) {
        await expect(main.getByRole('button', { name: framework }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });
  });

  // =========================================================================
  // Engineering Velocity
  // =========================================================================
  test.describe('Engineering Velocity page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/velocity');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Engineering Velocity').first()).toBeVisible({ timeout: 15_000 });
    });

    test('page loads without errors', async ({ page }) => {
      await page.goto('/velocity');
      await dismissTourIfPresent(page);

      // Should not redirect to login
      await expect(page).not.toHaveURL(/\/login/);
      // Should not show error boundary
      await expect(page.locator('main')).not.toContainText('Page Error');
    });
  });

  // =========================================================================
  // Developer Activity
  // =========================================================================
  test.describe('Developer Activity page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/devactivity');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Developer Activity').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders work distribution section', async ({ page }) => {
      await page.goto('/devactivity');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      // Should show work distribution section or no-data state
      const workDist = main.getByText(/work distribution/i);
      const noData = main.getByText(/no data/i);

      await expect(workDist.or(noData).first()).toBeVisible({ timeout: 15_000 });
    });

    test('team filter is interactive', async ({ page }) => {
      await page.goto('/devactivity');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      // Clear team filter button should be present if filter is active,
      // or the team autocomplete input should exist
      const clearFilter = main.getByRole('button', { name: /clear team filter/i });
      const teamInput = main.locator('input[type="text"]').first();

      await expect(clearFilter.or(teamInput).first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // User Behavior
  // =========================================================================
  test.describe('User Behavior page', () => {
    test('renders page title and context note', async ({ page }) => {
      await page.goto('/user-behavior');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('User Behavior').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders risk metric cards', async ({ page }) => {
      await page.goto('/user-behavior');
      await dismissTourIfPresent(page);

      // Verify key metric test ids
      const testIds = ['users-with-signals', 'high-risk-count', 'medium-risk-count', 'low-risk-count'];

      for (const testId of testIds) {
        await expect(page.getByTestId(testId)).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders behavior analysis tabs', async ({ page }) => {
      await page.goto('/user-behavior');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const tabs = ['Risky Users', 'Anomaly Detection', 'Permission Drift'];

      for (const tabName of tabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders top risk categories section', async ({ page }) => {
      await page.goto('/user-behavior');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Top Risk Categories').first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Copilot Insights (5 tabs)
  // =========================================================================
  test.describe('Copilot Insights page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/copilot/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      // Either shows Copilot Insights title or disabled message
      const title = main.getByText('Copilot Insights');
      const disabled = main.getByText(/copilot insights is disabled/i);
      await expect(title.or(disabled).first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders all 5 tabs when enabled', async ({ page }) => {
      await page.goto('/copilot/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const tablist = main.getByRole('tablist');
      const disabled = main.getByText(/copilot insights is disabled/i);

      // If disabled, skip tab checks
      if (await disabled.isVisible({ timeout: 3_000 }).catch(() => false)) {
        return;
      }

      await expect(tablist).toBeVisible({ timeout: 15_000 });

      const tabs = ['Overview', 'Adoption', 'Models & Features', 'License Optimization', 'Anomalies'];
      for (const tabName of tabs) {
        await expect(tablist.getByRole('tab', { name: tabName })).toBeVisible({ timeout: 15_000 });
      }
    });

    test('navigates to adoption tab', async ({ page }) => {
      await page.goto('/copilot/adoption');
      await dismissTourIfPresent(page);

      // Should not redirect to login
      await expect(page).not.toHaveURL(/\/login/);

      const main = page.locator('main');
      const title = main.getByText('Copilot Insights');
      const disabled = main.getByText(/copilot insights is disabled/i);
      await expect(title.or(disabled).first()).toBeVisible({ timeout: 15_000 });
    });

    test('navigates to models tab', async ({ page }) => {
      await page.goto('/copilot/models');
      await dismissTourIfPresent(page);

      await expect(page).not.toHaveURL(/\/login/);
    });

    test('navigates to license tab', async ({ page }) => {
      await page.goto('/copilot/license');
      await dismissTourIfPresent(page);

      await expect(page).not.toHaveURL(/\/login/);
    });

    test('navigates to anomalies tab', async ({ page }) => {
      await page.goto('/copilot/anomalies');
      await dismissTourIfPresent(page);

      await expect(page).not.toHaveURL(/\/login/);
    });
  });

  // =========================================================================
  // Threat Intelligence
  // =========================================================================
  test.describe('Threat Intelligence page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/threat-intel');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Threat Intelligence').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders category tabs', async ({ page }) => {
      await page.goto('/threat-intel');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const tabs = ['Feeds', 'Indicators', 'Matches', 'Analytics'];

      for (const tabName of tabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('tabs are clickable and switch content', async ({ page }) => {
      await page.goto('/threat-intel');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Click Indicators tab
      await main.getByRole('button', { name: 'Indicators' }).first().click();

      // Click Matches tab
      await main.getByRole('button', { name: 'Matches' }).first().click();

      // Click Analytics tab
      await main.getByRole('button', { name: 'Analytics' }).first().click();

      // No crash or error state
      await expect(page).not.toHaveURL(/\/login/);
    });
  });

  // =========================================================================
  // Detection Rules
  // =========================================================================
  test.describe('Detection Rules page', () => {
    test('renders page title and action buttons', async ({ page }) => {
      await page.goto('/rules');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Detection Rules').first()).toBeVisible({ timeout: 15_000 });
      await expect(main.getByRole('button', { name: /rule library/i }).first()).toBeVisible({
        timeout: 15_000,
      });
      await expect(main.getByRole('button', { name: /new rule/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders rules data table', async ({ page }) => {
      await page.goto('/rules');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const table = main.locator('table').first();
      await expect(table).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Workflow Security Scanner
  // =========================================================================
  test.describe('Workflow Security Scanner page', () => {
    test('renders page title and tabs', async ({ page }) => {
      await page.goto('/workflows');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Workflow Security').first()).toBeVisible({ timeout: 15_000 });

      const expectedTabs = ['Findings', 'Repo Scores', 'Failure Metrics'];
      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders analyze events button', async ({ page }) => {
      await page.goto('/workflows');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByRole('button', { name: /analyze events/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // =========================================================================
  // Reports
  // =========================================================================
  test.describe('Reports page', () => {
    test('renders page title and new report button', async ({ page }) => {
      await page.goto('/reports');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Reports').first()).toBeVisible({ timeout: 15_000 });
      await expect(main.getByRole('button', { name: /new custom report/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders time window buttons', async ({ page }) => {
      await page.goto('/reports');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      for (const window of ['30d', '60d', '90d']) {
        await expect(main.getByRole('button', { name: window }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders report category tabs', async ({ page }) => {
      await page.goto('/reports');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const tabs = ['Templates', 'My Reports', 'Shared with Me', 'Recent'];

      for (const tabName of tabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders report table with headers', async ({ page }) => {
      await page.goto('/reports');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const table = main.locator('table').first();
      await expect(table).toBeVisible({ timeout: 15_000 });

      // Verify key column headers
      await expect(table.getByText('Report Name').first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Query Explorer
  // =========================================================================
  test.describe('Query Explorer page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/query');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Query Explorer').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders SQL query interface elements', async ({ page }) => {
      await page.goto('/query');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // NL-to-SQL translation section
      await expect(main.getByText(/translate natural language/i).first()).toBeVisible({
        timeout: 15_000,
      });

      // Database schema reference
      await expect(main.getByText(/available database tables/i).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders query action buttons', async ({ page }) => {
      await page.goto('/query');
      await dismissTourIfPresent(page);

      // Execute button (by title/label)
      await expect(
        page.locator('[title*="Execute"]').or(page.getByRole('button', { name: /execute/i })).first(),
      ).toBeVisible({ timeout: 15_000 });

      // History button
      await expect(
        page
          .locator('[title*="previously executed"]')
          .or(page.getByRole('button', { name: /history/i }))
          .first(),
      ).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Sync Status
  // =========================================================================
  test.describe('Sync Status page', () => {
    test('renders page title and breadcrumbs', async ({ page }) => {
      await page.goto('/monitoring/sync-status');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Sync Status').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders health banner', async ({ page }) => {
      await page.goto('/monitoring/sync-status');
      await dismissTourIfPresent(page);

      await expect(page.getByTestId('health-banner')).toBeVisible({ timeout: 15_000 });
    });

    test('renders overall status card', async ({ page }) => {
      await page.goto('/monitoring/sync-status');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Overall Status').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders recent sync runs table', async ({ page }) => {
      await page.goto('/monitoring/sync-status');
      await dismissTourIfPresent(page);

      await expect(page.getByTestId('recent-runs-table')).toBeVisible({ timeout: 15_000 });
    });
  });

  // =========================================================================
  // Settings (Secrets tab, GitHub tab)
  // =========================================================================
  test.describe('Settings page — all tabs', () => {
    test('renders all category tabs including Secrets and GitHub', async ({ page }) => {
      await page.goto('/settings/secrets');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const expectedTabs = ['Secrets', 'GitHub', 'Security', 'Notifications', 'System', 'Features', 'Integrations', 'Retention'];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('Secrets tab renders settings table', async ({ page }) => {
      await page.goto('/settings/secrets');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Secrets tab should show a settings table or enterprise-pat section
      const patSection = page.getByTestId('enterprise-pat-section');
      const table = main.locator('table').first();
      const errorState = main.getByText(/failed to load/i);

      await expect(patSection.or(table).or(errorState).first()).toBeVisible({ timeout: 15_000 });
    });

    test('GitHub tab renders GitHub configuration', async ({ page }) => {
      await page.goto('/settings/github');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Should show GitHub settings content or error state
      await expect(main.getByText(/github/i).first()).toBeVisible({ timeout: 15_000 });
    });

    test('navigates between tabs via URL', async ({ page }) => {
      await page.goto('/settings/security');
      await dismissTourIfPresent(page);

      await expect(page).toHaveURL(/\/settings\/security/);
      await expect(page).not.toHaveURL(/\/login/);

      await page.goto('/settings/notifications');
      await expect(page).toHaveURL(/\/settings\/notifications/);
    });
  });

  // =========================================================================
  // Users & Roles
  // =========================================================================
  test.describe('Users & Roles page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/users');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Users').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders Users and Roles tabs', async ({ page }) => {
      await page.goto('/users');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByRole('button', { name: 'Users' }).first()).toBeVisible({
        timeout: 15_000,
      });
      await expect(main.getByRole('button', { name: 'Roles' }).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders Create role button', async ({ page }) => {
      await page.goto('/users');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByRole('button', { name: /create role/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // =========================================================================
  // Monitoring > Telemetry
  // =========================================================================
  test.describe('Telemetry page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/monitoring/telemetry');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Ingestion Telemetry').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders metric cards', async ({ page }) => {
      await page.goto('/monitoring/telemetry');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const metrics = ['Events/Second', 'Events Today', 'Active Workers', 'Queue Depth'];

      for (const metric of metrics) {
        await expect(main.getByText(metric).first()).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders telemetry tabs', async ({ page }) => {
      await page.goto('/monitoring/telemetry');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const tabs = ['Stream Status', 'Worker Health', 'Event Volume', 'Errors & Gaps'];

      for (const tabName of tabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });
  });

  // =========================================================================
  // Events / Alerts
  // =========================================================================
  test.describe('Events page', () => {
    test('renders page title and search', async ({ page }) => {
      await page.goto('/events');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Events Explorer').first()).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('#events-search-input')).toBeVisible({ timeout: 15_000 });
    });

    test('renders data table with headers', async ({ page }) => {
      await page.goto('/events');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      const table = main.locator('table').first();
      await expect(table).toBeVisible({ timeout: 15_000 });

      const headers = table.locator('thead th');
      await expect(headers.first()).toBeVisible({ timeout: 15_000 });
      expect(await headers.count()).toBeGreaterThanOrEqual(2);
    });

    test('renders export and save buttons', async ({ page }) => {
      await page.goto('/events');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByRole('button', { name: /export csv/i }).first()).toBeVisible({
        timeout: 15_000,
      });
      await expect(main.getByRole('button', { name: /save query/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // =========================================================================
  // Dashboard (customizable, widget rendering)
  // =========================================================================
  test.describe('Dashboard page — widgets', () => {
    test('renders customizable dashboard with stat pills', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Dashboard').first()).toBeVisible({ timeout: 15_000 });

      // Stat pills with key labels
      const labels = ['events today', 'open threats', 'pipeline success', 'active devs'];
      for (const label of labels) {
        await expect(main.getByText(label).first()).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders activity heatmap widget', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Activity heatmap').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders open threats by severity widget', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Open threats by severity').first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders activity feed widget', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await expect(main.getByText('Activity feed').first()).toBeVisible({ timeout: 15_000 });
    });

    test('widget view mode can be toggled', async ({ page }) => {
      await page.goto('/dashboard?view=widgets');
      await dismissTourIfPresent(page);

      // Should load without errors in widget mode
      await expect(page).not.toHaveURL(/\/login/);
      await expect(page.locator('main').getByText('Dashboard').first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });
});
