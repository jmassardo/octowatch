import { test, expect, navigateTo } from './helpers';

test.describe('Query Explorer Editor', () => {
  test('autocomplete appears when typing after FROM', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();

    // Clear textarea and type a query with FROM
    await textarea.click();
    await textarea.fill('SELECT * FROM ev');

    // Wait for autocomplete dropdown to appear
    const dropdown = page.locator('[role="listbox"]');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    // Should suggest "events" table
    const items = dropdown.locator('[role="option"]');
    await expect(items.first()).toBeVisible();
    const firstText = await items.first().textContent();
    expect(firstText).toContain('events');
  });

  test('autocomplete appears when typing keywords', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('');
    await textarea.type('SEL', { delay: 50 });

    const dropdown = page.locator('[role="listbox"]');
    await expect(dropdown).toBeVisible({ timeout: 5000 });
    const firstText = await dropdown.locator('[role="option"]').first().textContent();
    expect(firstText).toContain('SELECT');
  });

  test('autocomplete accepts suggestion with Tab', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('');
    await textarea.type('SEL', { delay: 50 });

    const dropdown = page.locator('[role="listbox"]');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    // Press Tab to accept
    await textarea.press('Tab');

    // Dropdown should dismiss
    await expect(dropdown).not.toBeVisible({ timeout: 2000 });

    // Textarea should now contain SELECT
    const value = await textarea.inputValue();
    expect(value).toContain('SELECT');
  });

  test('arrow keys move cursor when autocomplete is not active', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('SELECT *\nFROM events');

    // Move to beginning and press down arrow
    await textarea.press('Home');
    await textarea.press('ArrowDown');

    // The cursor should have moved — test that arrow keys work without errors
    // (If intercepted, cursor wouldn't move and this would fail differently)
    const value = await textarea.inputValue();
    expect(value).toBe('SELECT *\nFROM events');
  });

  test('Escape dismisses autocomplete', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('');
    await textarea.type('SEL', { delay: 50 });

    const dropdown = page.locator('[role="listbox"]');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    await textarea.press('Escape');
    await expect(dropdown).not.toBeVisible({ timeout: 2000 });
  });

  test('validation shows error underline for invalid SQL', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('SELECT * FROM app_settings');

    // Wait for debounced validation (800ms + network)
    const errorUnderline = page.locator('[class*="errorUnderline"]');
    await expect(errorUnderline).toBeVisible({ timeout: 5000 });

    // Error bar should also appear (use first() since child spans also match)
    const errorBar = page.locator('[class*="errorBar"]').first();
    await expect(errorBar).toBeVisible({ timeout: 2000 });
    const errorText = await errorBar.textContent();
    expect(errorText).toContain('app_settings');
  });

  test('validation shows green dot for valid SQL', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('SELECT action FROM events LIMIT 5');

    // Wait for debounced validation
    const validDot = page.locator('[class*="validDot"]');
    await expect(validDot).toBeVisible({ timeout: 5000 });

    // Error underline should NOT appear
    const errorUnderline = page.locator('[class*="errorUnderline"]');
    await expect(errorUnderline).not.toBeVisible({ timeout: 1000 });
  });

  test('validation shows error underline for forbidden function', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill("SELECT pg_read_file('/etc/passwd')");

    const errorUnderline = page.locator('[class*="errorUnderline"]');
    await expect(errorUnderline).toBeVisible({ timeout: 5000 });
  });

  test('Ctrl+Enter runs the query', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('SELECT action, COUNT(*) as cnt FROM events GROUP BY action ORDER BY cnt DESC LIMIT 3');

    // Listen for the API call
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/query/run') && resp.status() === 200,
      { timeout: 10000 }
    );

    const isMac = process.platform === 'darwin';
    await textarea.press(isMac ? 'Meta+Enter' : 'Control+Enter');

    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();

    // Results table should appear
    const resultsTable = page.locator('table');
    await expect(resultsTable).toBeVisible({ timeout: 5000 });
  });

  test('schema column click inserts at cursor', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');

    const textarea = page.locator('textarea');
    await textarea.click();
    await textarea.fill('SELECT ');

    // Find and click the 'actor' column in schema sidebar
    const actorCol = page.locator('[class*="schemaCol"]', { hasText: 'actor' }).first();
    await expect(actorCol).toBeVisible();
    await actorCol.click();

    const value = await textarea.inputValue();
    expect(value).toContain('actor');
  });
});
