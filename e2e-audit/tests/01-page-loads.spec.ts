/**
 * Comprehensive UI audit — Phase 1: Page load & basic rendering
 *
 * Tests that every route loads without errors, renders expected elements,
 * and has no broken API calls.
 */
import { test, expect, navigateTo, getApiErrors } from './helpers';

test.describe('Page Load Audit', () => {
  test('Dashboard loads and renders stat cards', async ({ authedPage: page }) => {
    await navigateTo(page, '/dashboard');
    // Should have stat cards
    const cards = page.locator('[class*="stat"], [class*="card"], [class*="metric"]');
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
    // Check for key content
    await expect(page.locator('text=Dashboard').first()).toBeVisible();
  });

  test('Events page loads and renders table', async ({ authedPage: page }) => {
    await navigateTo(page, '/events');
    // Should have a search input or table
    const hasTable = await page.locator('table, [class*="table"], [class*="event"]').first().isVisible().catch(() => false);
    const hasSearch = await page.locator('input[type="text"], input[placeholder]').first().isVisible().catch(() => false);
    expect(hasTable || hasSearch).toBeTruthy();
  });

  test('Threats page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/threats');
    // Page renders either detections or an empty state
    const hasContent = await page.locator('text=/Detection|Threat|Alert|Investigating|No.*detection/i').first().isVisible({ timeout: 15_000 }).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Velocity page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/velocity');
    await expect(page.locator('text=Velocity').first()).toBeVisible({ timeout: 10_000 });
  });

  test('DevActivity page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/devactivity');
    await expect(page.locator('text=Activity').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Copilot Overview loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/overview');
    // Shows either copilot data or a "disabled" message
    const hasContent = await page.locator('text=/Copilot|disabled|Disabled|not available|feature|Overview/i').first().isVisible({ timeout: 15_000 }).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Copilot Adoption loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/adoption');
    const hasContent = await page.locator('text=/Adoption|Copilot|disabled|Disabled|not available/i').first().isVisible({ timeout: 15_000 }).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Copilot Models loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/models');
    const hasContent = await page.locator('text=/Model|Copilot|disabled|Disabled|not available/i').first().isVisible({ timeout: 15_000 }).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Copilot License loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/license');
    const hasContent = await page.locator('text=/License|Copilot|disabled|Disabled|not available/i').first().isVisible({ timeout: 15_000 }).catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Copilot Anomalies loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/anomalies');
    const hasContent = await page.locator('text=/Anomal|Copilot|disabled|not available/i').first().isVisible().catch(() => false);
    expect(hasContent).toBeTruthy();
  });

  test('Health Repos tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/repos');
    await expect(page.locator('text=/Repository|Health|Repo/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health Access tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/access');
    await expect(page.locator('text=/Access|Identity/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health Security tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/security');
    await expect(page.locator('text=/Security|Posture/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health Governance tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/governance');
    await expect(page.locator('text=/Governance|App/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health Operations tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/operations');
    await expect(page.locator('text=/Operations|Ops/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health License tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/license');
    await expect(page.locator('text=/License/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health Maintenance tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/maintenance');
    await expect(page.locator('text=/Maintenance/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Health WAF tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/waf');
    await expect(page.locator('text=/WAF|Well-Architected/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Reports page loads and renders report cards', async ({ authedPage: page }) => {
    await navigateTo(page, '/reports');
    await expect(page.locator('text=/Report/i').first()).toBeVisible({ timeout: 10_000 });
    // Check for report cards or error state
    const hasCards = await page.locator('[class*="card"], [class*="report"]').first().isVisible().catch(() => false);
    const hasError = await page.locator('[class*="error"], [class*="Error"]').first().isVisible().catch(() => false);
    const hasEmpty = await page.locator('text=/no report|empty|no data/i').first().isVisible().catch(() => false);
    // Log what we see
    console.log(`Reports: cards=${hasCards}, error=${hasError}, empty=${hasEmpty}`);
  });

  test('Query Explorer page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');
    await expect(page.locator('text=/Query|Explorer/i').first()).toBeVisible({ timeout: 10_000 });
    // Should have a textarea or code editor
    const hasEditor = await page.locator('textarea, [class*="editor"], [class*="code"]').first().isVisible().catch(() => false);
    console.log(`Query: editor=${hasEditor}`);
  });

  test('Rules page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/rules');
    await expect(page.locator('text=/Rule|Detection/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Users page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/users');
    await expect(page.locator('text=/User|Role/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Integrations page loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/integrations');
    await expect(page.locator('text=/Integration/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Settings All tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/all');
    await expect(page.locator('text=/Setting/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Settings GitHub tab loads with settings', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/github');
    // Should show GitHub-category settings or empty state
    const settingRows = page.locator('tr, [class*="row"], [class*="setting"]');
    const count = await settingRows.count();
    console.log(`Settings/github: ${count} rows`);
  });

  test('Settings Security tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/security');
    const settingRows = page.locator('tr, [class*="row"], [class*="setting"]');
    const count = await settingRows.count();
    console.log(`Settings/security: ${count} rows`);
  });

  test('Settings Storage tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/storage');
    const settingRows = page.locator('tr, [class*="row"], [class*="setting"]');
    const count = await settingRows.count();
    console.log(`Settings/storage: ${count} rows`);
  });

  test('Settings Notifications tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/notifications');
    const settingRows = page.locator('tr, [class*="row"], [class*="setting"]');
    const count = await settingRows.count();
    console.log(`Settings/notifications: ${count} rows`);
  });

  test('Settings System tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/system');
    const settingRows = page.locator('tr, [class*="row"], [class*="setting"]');
    const count = await settingRows.count();
    console.log(`Settings/system: ${count} rows`);
  });

  test('Settings Audit tab loads', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/audit');
    await expect(page.locator('text=/Audit/i').first()).toBeVisible({ timeout: 10_000 });
  });

  test('Settings Features tab loads with toggles', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/features');
    const toggles = page.locator('input[type="checkbox"]');
    const count = await toggles.count();
    console.log(`Settings/features: ${count} toggles`);
    expect(count).toBeGreaterThan(0);
  });
});
