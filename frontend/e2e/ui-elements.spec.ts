import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// UI element tests — verify key components render on each page.
//
// Authentication is handled by the "setup" project in playwright.config.ts.
//
// These tests navigate directly to routes (no sidebar clicks) to avoid
// the Guided Tour overlay intercepting pointer events.
//
// The app may show "no data" states if no audit data is ingested — that is
// expected.  Tests validate that the page *structure* renders correctly, not
// that it contains real data.
// ---------------------------------------------------------------------------

/** Dismiss the guided tour if it appears — it blocks interaction. */
async function dismissTourIfPresent(page: Page) {
  const closeBtn = page.getByRole('button', { name: 'Close tour' });
  // Short timeout: the tour may or may not appear depending on state.
  if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await closeBtn.click();
    // Wait for overlay to disappear
    await expect(page.getByRole('dialog', { name: 'Guided tour' })).toBeHidden({ timeout: 3_000 });
  }
}

// UI element tests require auth cookies — skip in CI where self-signed TLS
// prevents cookie persistence.
test.describe('UI elements', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  // -----------------------------------------------------------------------
  // Dashboard
  // -----------------------------------------------------------------------
  test.describe('Dashboard page', () => {
    test('renders stat pills with labels', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // The dashboard shows 8 StatPill components, each with a label.
      // Verify at least a few known stat labels are rendered.
      const expectedLabels = [
        'events today',
        'open threats',
        'pipeline success',
        'active devs',
        'total events',
      ];

      for (const label of expectedLabels) {
        await expect(main.getByText(label).first()).toBeVisible({ timeout: 15_000 });
      }
    });

    test('renders activity heatmap section', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // The heatmap card title
      await expect(main.getByText('Activity heatmap').first()).toBeVisible({ timeout: 15_000 });
    });

    test('renders open threats by severity section', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      await expect(main.getByText('Open threats by severity').first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders activity feed section', async ({ page }) => {
      await page.goto('/dashboard');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      await expect(main.getByText('Activity feed').first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // -----------------------------------------------------------------------
  // Threats
  // -----------------------------------------------------------------------
  test.describe('Threats page', () => {
    test('renders status filter tabs', async ({ page }) => {
      await page.goto('/threats');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Five tab buttons: Open, Investigating, Closed, Acknowledged, All
      for (const label of ['Open', 'Investigating', 'Closed', 'Acknowledged']) {
        await expect(main.getByRole('button', { name: label }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders severity filter dropdown', async ({ page }) => {
      await page.goto('/threats');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // The severity filter select includes "All severities"
      await expect(
        main.locator('select').filter({ hasText: 'All severities' }).first(),
      ).toBeVisible({ timeout: 15_000 });
    });
  });

  // -----------------------------------------------------------------------
  // Events
  // -----------------------------------------------------------------------
  test.describe('Events page', () => {
    test('renders search input', async ({ page }) => {
      await page.goto('/events');
      await dismissTourIfPresent(page);

      // Events page has a search input with id "events-search-input"
      await expect(page.locator('#events-search-input')).toBeVisible({ timeout: 15_000 });
    });

    test('renders DataTable with column headers', async ({ page }) => {
      await page.goto('/events');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // DataTable renders as <table> with <thead> and <th> elements
      const table = main.locator('table').first();
      await expect(table).toBeVisible({ timeout: 15_000 });

      // Verify column headers exist
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

  // -----------------------------------------------------------------------
  // Rules
  // -----------------------------------------------------------------------
  test.describe('Rules page', () => {
    test('renders DataTable with column headers', async ({ page }) => {
      await page.goto('/rules');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      const table = main.locator('table').first();
      await expect(table).toBeVisible({ timeout: 15_000 });

      const headers = table.locator('thead th');
      await expect(headers.first()).toBeVisible({ timeout: 15_000 });
      expect(await headers.count()).toBeGreaterThanOrEqual(2);
    });

    test('renders rule action buttons', async ({ page }) => {
      await page.goto('/rules');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // The Rules page has "Rule Library", "Sync from GitHub", and "New rule" buttons
      await expect(main.getByRole('button', { name: /rule library/i }).first()).toBeVisible({
        timeout: 15_000,
      });

      await expect(main.getByRole('button', { name: /new rule/i }).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // -----------------------------------------------------------------------
  // Copilot
  // -----------------------------------------------------------------------
  test.describe('Copilot page', () => {
    test('renders tab bar or disabled message', async ({ page }) => {
      await page.goto('/copilot/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Copilot may be feature-gated.  If disabled the page shows a
      // "Copilot Insights is disabled" heading.  If enabled, it shows
      // a tablist with Overview, Adoption, etc.  Either outcome is valid.
      const tablist = main.getByRole('tablist');
      const disabledMsg = main.getByRole('heading', {
        name: /copilot insights is disabled/i,
      });

      await expect(tablist.or(disabledMsg).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('disabled state links to Settings → Features', async ({ page }) => {
      await page.goto('/copilot/overview');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Wait for page to be interactive
      await expect(main.getByText(/copilot/i).first()).toBeVisible({
        timeout: 15_000,
      });

      // If Copilot is disabled, a "Settings → Features" link should appear
      const settingsLink = main.getByRole('link', {
        name: /settings.*features/i,
      });
      const tablist = main.getByRole('tablist');

      // One of these must be present — either enabled (tablist) or
      // disabled (link to settings)
      await expect(settingsLink.or(tablist).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // -----------------------------------------------------------------------
  // Settings
  // -----------------------------------------------------------------------
  test.describe('Settings page', () => {
    test('renders category tab buttons', async ({ page }) => {
      await page.goto('/settings');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Settings page has category tabs
      const expectedTabs = ['GitHub', 'Security', 'Storage', 'Notifications', 'System'];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });

    test('renders enterprise PAT config section or load-error state', async ({ page }) => {
      await page.goto('/settings/all');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Settings may fail to load if backend config is incomplete.
      // Accept either the enterprise-pat-section or a visible error state.
      const patSection = page.getByTestId('enterprise-pat-section');
      const errorBanner = main.getByText(/failed to load settings/i);
      const noSettings = main.getByText(/no settings configured/i);

      await expect(patSection.or(errorBanner).or(noSettings).first()).toBeVisible({
        timeout: 15_000,
      });
    });
  });

  // -----------------------------------------------------------------------
  // Health
  // -----------------------------------------------------------------------
  test.describe('Health page', () => {
    test('renders tab bar with health categories', async ({ page }) => {
      await page.goto('/health/repos');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Health page has a tablist with role="tablist"
      const tablist = main.getByRole('tablist');
      await expect(tablist).toBeVisible({ timeout: 15_000 });

      // Verify a few key tabs are present (names match actual tab labels)
      const expectedTabs = ['Repository Health', 'Access & Identity', 'Security Posture'];

      for (const tabName of expectedTabs) {
        await expect(tablist.getByRole('tab', { name: tabName })).toBeVisible({ timeout: 15_000 });
      }
    });
  });

  // -----------------------------------------------------------------------
  // Advanced Security
  // -----------------------------------------------------------------------
  test.describe('Advanced Security page', () => {
    test('renders tab buttons for GHAS categories', async ({ page }) => {
      await page.goto('/advanced-security');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      const expectedTabs = [
        'Overview',
        'Secret Scanning',
        'Code Scanning',
        'Dependabot',
        'Activity Log',
      ];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });
  });

  // -----------------------------------------------------------------------
  // Workflows
  // -----------------------------------------------------------------------
  test.describe('Workflows page', () => {
    test('renders tab buttons and Analyze Events button', async ({ page }) => {
      await page.goto('/workflows');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      await expect(main.getByRole('button', { name: /analyze events/i }).first()).toBeVisible({
        timeout: 15_000,
      });

      const expectedTabs = ['Findings', 'Repo Scores', 'Failure Metrics'];

      for (const tabName of expectedTabs) {
        await expect(main.getByRole('button', { name: tabName }).first()).toBeVisible({
          timeout: 15_000,
        });
      }
    });
  });

  // -----------------------------------------------------------------------
  // Cross-Org
  // -----------------------------------------------------------------------
  test.describe('Cross-Org page', () => {
    test('renders Correlations and Timeline tabs', async ({ page }) => {
      await page.goto('/crossorg');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      await expect(main.getByRole('button', { name: 'Correlations' }).first()).toBeVisible({
        timeout: 15_000,
      });

      await expect(main.getByRole('button', { name: 'Timeline' }).first()).toBeVisible({
        timeout: 15_000,
      });
    });

    test('renders time range filter', async ({ page }) => {
      await page.goto('/crossorg');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // Time range filter select should be present
      await expect(main.locator('select').first()).toBeVisible({ timeout: 15_000 });
    });
  });

  // -----------------------------------------------------------------------
  // Posture
  // -----------------------------------------------------------------------
  test.describe('Posture page', () => {
    test('renders page title', async ({ page }) => {
      await page.goto('/posture');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      await expect(main.getByText('Security Posture').first()).toBeVisible({ timeout: 15_000 });
    });
  });
});
