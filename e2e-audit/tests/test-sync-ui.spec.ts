import { test, navigateTo, expect } from './helpers';

test('sync panel displays correctly', async ({ authedPage: page }) => {
  await navigateTo(page, '/integrations');
  await page.waitForTimeout(2000);
  
  // Check what's visible
  const progressBar = page.locator('[data-testid="sync-progress"]');
  const entityTable = page.locator('[data-testid="entity-table"]');
  const syncStatus = page.locator('[data-testid="sync-status"]');
  
  console.log('Progress bar visible:', await progressBar.isVisible().catch(() => false));
  console.log('Entity table visible:', await entityTable.isVisible().catch(() => false));
  console.log('Sync status visible:', await syncStatus.isVisible().catch(() => false));
  
  // Check API response
  const resp = await page.request.get('https://localhost/api/v1/admin/sync/status', { ignoreHTTPSErrors: true });
  console.log('API status:', resp.status());
  const body = await resp.json().catch(() => null);
  console.log('API body:', JSON.stringify(body, null, 2)?.substring(0, 500));
  
  await page.screenshot({ path: '/tmp/sync-panel-debug.png', fullPage: true });
});
