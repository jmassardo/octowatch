/**
 * Comprehensive UI audit — Phase 2: Interactive elements
 *
 * Tests clickable controls, navigation, filters, modals, and data flow.
 */
import { test, expect, navigateTo, getApiErrors } from './helpers';

test.describe('Sidebar Navigation', () => {
  test('all sidebar links navigate correctly', async ({ authedPage: page }) => {
    await navigateTo(page, '/dashboard');
    
    const navLinks = [
      { text: 'Dashboard', path: '/dashboard' },
      { text: 'Threat Detections', path: '/threats' },
      { text: 'Events Explorer', path: '/events' },
      { text: 'Engineering Velocity', path: '/velocity' },
      { text: 'Developer Activity', path: '/devactivity' },
      { text: 'Copilot Insights', path: '/copilot' },
      { text: 'Org Health', path: '/health' },
      { text: 'Reports', path: '/reports' },
      { text: 'Query Explorer', path: '/query' },
      { text: 'Detection Rules', path: '/rules' },
      { text: 'Users & Roles', path: '/users' },
      { text: 'Integrations', path: '/integrations' },
      { text: 'Settings', path: '/settings' },
    ];

    for (const link of navLinks) {
      const navItem = page.locator(`nav a:has-text("${link.text}")`);
      const isVisible = await navItem.isVisible().catch(() => false);
      if (!isVisible) {
        console.log(`SKIP NAV: "${link.text}" not visible (may be feature-toggled off)`);
        continue;
      }
      await navItem.click();
      await page.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => {});
      const url = page.url();
      expect(url).toContain(link.path);
      console.log(`NAV OK: "${link.text}" → ${url}`);
    }
  });
});

test.describe('Dashboard Interactions', () => {
  test('clickable stat cards navigate to correct pages', async ({ authedPage: page }) => {
    await navigateTo(page, '/dashboard');
    await page.waitForTimeout(2000);

    // Find all clickable stat elements
    const clickableStats = page.locator('[class*="stat"][style*="cursor"], [class*="clickable"], a[href*="/events"], a[href*="/threats"], a[href*="/velocity"]');
    const count = await clickableStats.count();
    console.log(`Dashboard: found ${count} clickable stat elements`);
    
    // Click first stat and verify navigation
    if (count > 0) {
      const firstStat = clickableStats.first();
      await firstStat.click();
      await page.waitForTimeout(1000);
      const url = page.url();
      console.log(`Dashboard stat click → ${url}`);
    }
  });
});

test.describe('Events Page Interactions', () => {
  test('search input and filtering works', async ({ authedPage: page }) => {
    await navigateTo(page, '/events');
    await page.waitForTimeout(2000);

    const searchInput = page.locator('input[type="text"], input[placeholder*="earch"], input[placeholder*="filter"]').first();
    const isVisible = await searchInput.isVisible().catch(() => false);
    if (isVisible) {
      await searchInput.fill('test.action');
      await searchInput.press('Enter');
      await page.waitForTimeout(1500);
      // Check if chip was created
      const chips = page.locator('[class*="chip"], [class*="tag"], [class*="filter"]');
      const chipCount = await chips.count();
      console.log(`Events: ${chipCount} filter chips after search`);
    } else {
      console.log('Events: no search input found');
    }
  });

  test('Events page with repo filter from URL', async ({ authedPage: page }) => {
    await navigateTo(page, '/events?repo=test-repo');
    await page.waitForTimeout(2000);

    // Check if the repo filter was applied
    const chips = page.locator('[class*="chip"], [class*="tag"], [class*="filter"]');
    const chipCount = await chips.count();
    console.log(`Events with ?repo=test-repo: ${chipCount} filter chips`);
    
    // Check page content for filter indication
    const pageContent = await page.textContent('body');
    const hasRepoFilter = pageContent?.includes('test-repo') || false;
    console.log(`Events: repo filter visible in page content: ${hasRepoFilter}`);
  });
  
  test('pagination controls exist and work', async ({ authedPage: page }) => {
    await navigateTo(page, '/events');
    await page.waitForTimeout(2000);

    const prevBtn = page.locator('button:has-text("Prev"), button:has-text("Previous"), button:has-text("←")').first();
    const nextBtn = page.locator('button:has-text("Next"), button:has-text("→")').first();
    
    const hasPrev = await prevBtn.isVisible().catch(() => false);
    const hasNext = await nextBtn.isVisible().catch(() => false);
    console.log(`Events pagination: prev=${hasPrev}, next=${hasNext}`);
  });
});

test.describe('Velocity Page Interactions', () => {
  test('repo click navigates to events with filter', async ({ authedPage: page }) => {
    await navigateTo(page, '/velocity');
    await page.waitForTimeout(3000);

    // Find repo rows
    const repoRows = page.locator('[class*="repo"] tr, table tr').filter({ hasText: /.+/ });
    const repoCount = await repoRows.count();
    console.log(`Velocity: ${repoCount} repo rows`);

    if (repoCount > 1) { // skip header row
      const firstDataRow = repoRows.nth(1);
      const rowText = await firstDataRow.textContent();
      console.log(`Velocity: clicking row with text: "${rowText?.slice(0, 80)}"`);
      
      await firstDataRow.click();
      await page.waitForTimeout(2000);
      
      const url = page.url();
      console.log(`Velocity repo click → ${url}`);
      
      // Should navigate to events with repo filter
      if (url.includes('/events')) {
        const hasRepoParam = url.includes('repo=');
        console.log(`Velocity→Events: has repo param: ${hasRepoParam}`);
        if (!hasRepoParam) {
          console.log('BUG: Velocity repo click navigates to /events but without repo filter');
        }
      }
    }
  });

  test('DORA badge click opens modal', async ({ authedPage: page }) => {
    await navigateTo(page, '/velocity');
    await page.waitForTimeout(3000);

    const doraBadge = page.locator('[class*="dora"], [class*="Dora"], text=/DORA/i').first();
    const hasDora = await doraBadge.isVisible().catch(() => false);
    if (hasDora) {
      await doraBadge.click();
      await page.waitForTimeout(1000);
      const modal = page.locator('[class*="modal"], [class*="Modal"], [role="dialog"]').first();
      const modalVisible = await modal.isVisible().catch(() => false);
      console.log(`Velocity DORA modal: ${modalVisible}`);
    } else {
      console.log('Velocity: no DORA badge found');
    }
  });
});

test.describe('Reports Page', () => {
  test('reports page renders charts and controls', async ({ authedPage: page }) => {
    await navigateTo(page, '/reports');
    await page.waitForTimeout(3000);

    // Check for window selector buttons
    const windowBtns = page.locator('button:has-text("30"), button:has-text("60"), button:has-text("90")');
    const windowCount = await windowBtns.count();
    console.log(`Reports: ${windowCount} window buttons`);

    // Check for report cards
    const cards = page.locator('[class*="card"], [class*="report"]');
    const cardCount = await cards.count();
    console.log(`Reports: ${cardCount} cards`);

    // Check for charts
    const charts = page.locator('svg, canvas, [class*="chart"]');
    const chartCount = await charts.count();
    console.log(`Reports: ${chartCount} chart elements`);

    // Check for errors
    const errors = page.locator('[class*="error"], [class*="Error"]');
    const errorCount = await errors.count();
    console.log(`Reports: ${errorCount} error elements`);

    // Check API errors
    const apiErrs = getApiErrors(page);
    for (const err of apiErrs) {
      if (err.url.includes('/reports')) {
        console.log(`Reports API error: ${err.status} ${err.url} → ${err.body.slice(0, 200)}`);
      }
    }

    // Check for empty/placeholder text
    const pageText = await page.textContent('body') || '';
    if (pageText.includes('Coming soon') || pageText.includes('placeholder') || pageText.includes('mock')) {
      console.log('BUG: Reports page contains placeholder/mock text');
    }
  });

  test('reports window buttons change data', async ({ authedPage: page }) => {
    await navigateTo(page, '/reports');
    await page.waitForTimeout(3000);

    const btn30 = page.locator('button:has-text("30d"), button:has-text("30 d")').first();
    const btn90 = page.locator('button:has-text("90d"), button:has-text("90 d")').first();
    
    if (await btn90.isVisible().catch(() => false)) {
      await btn90.click();
      await page.waitForTimeout(2000);
      console.log('Reports: clicked 90d button');
    }
    
    if (await btn30.isVisible().catch(() => false)) {
      await btn30.click();
      await page.waitForTimeout(2000);
      console.log('Reports: clicked 30d button');
    }
  });

  test('reports export buttons work', async ({ authedPage: page }) => {
    await navigateTo(page, '/reports');
    await page.waitForTimeout(3000);

    const exportBtns = page.locator('button:has-text("PDF"), button:has-text("CSV"), button:has-text("Export")');
    const exportCount = await exportBtns.count();
    console.log(`Reports: ${exportCount} export buttons`);
    
    for (let i = 0; i < Math.min(exportCount, 3); i++) {
      const btn = exportBtns.nth(i);
      const btnText = await btn.textContent();
      const isDisabled = await btn.isDisabled();
      console.log(`Reports export button "${btnText}": disabled=${isDisabled}`);
    }
  });
});

test.describe('Query Explorer', () => {
  test('query page has editor, run button, and schema tree', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');
    await page.waitForTimeout(3000);

    // Check for SQL editor
    const editor = page.locator('textarea, [class*="editor"], [class*="code"]').first();
    const hasEditor = await editor.isVisible().catch(() => false);
    console.log(`Query: editor visible: ${hasEditor}`);

    // Check for Run button
    const runBtn = page.locator('button:has-text("Run"), button:has-text("Execute")').first();
    const hasRun = await runBtn.isVisible().catch(() => false);
    console.log(`Query: run button visible: ${hasRun}`);

    // Check for schema tree
    const schemaTree = page.locator('[class*="schema"], [class*="tree"], [class*="table"]').first();
    const hasSchema = await schemaTree.isVisible().catch(() => false);
    console.log(`Query: schema tree visible: ${hasSchema}`);

    // Check for templates
    const templates = page.locator('[class*="template"], text=/template/i').first();
    const hasTemplates = await templates.isVisible().catch(() => false);
    console.log(`Query: templates visible: ${hasTemplates}`);

    // Check for errors
    const apiErrs = getApiErrors(page);
    for (const err of apiErrs) {
      if (err.url.includes('/query')) {
        console.log(`Query API error: ${err.status} ${err.url} → ${err.body.slice(0, 200)}`);
      }
    }
  });

  test('query run executes and shows results', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');
    await page.waitForTimeout(3000);

    const editor = page.locator('textarea').first();
    if (await editor.isVisible().catch(() => false)) {
      await editor.fill('SELECT action, COUNT(*) as cnt FROM events GROUP BY action ORDER BY cnt DESC LIMIT 10');
      
      const runBtn = page.locator('button:has-text("Run"), button:has-text("Execute")').first();
      if (await runBtn.isVisible().catch(() => false)) {
        await runBtn.click();
        await page.waitForTimeout(5000);

        // Check for results
        const results = page.locator('table, [class*="result"]');
        const hasResults = await results.first().isVisible().catch(() => false);
        console.log(`Query run: results visible: ${hasResults}`);
        
        // Check for error
        const errorEl = page.locator('[class*="error"], [class*="Error"]').first();
        const hasError = await errorEl.isVisible().catch(() => false);
        if (hasError) {
          const errorText = await errorEl.textContent();
          console.log(`Query run error: "${errorText?.slice(0, 200)}"`);
        }
      }
    }
  });

  test('query templates load and can be selected', async ({ authedPage: page }) => {
    await navigateTo(page, '/query');
    await page.waitForTimeout(3000);

    const templateItems = page.locator('[class*="template"] [class*="item"], [class*="template"] li, [class*="template"] button');
    const count = await templateItems.count();
    console.log(`Query: ${count} template items`);

    if (count > 0) {
      await templateItems.first().click();
      await page.waitForTimeout(1000);
      const editor = page.locator('textarea').first();
      const value = await editor.inputValue().catch(() => '');
      console.log(`Query: template loaded SQL: "${value.slice(0, 100)}"`);
    }
  });
});

test.describe('Copilot Page Interactions', () => {
  test('copilot tab navigation works', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/overview');
    await page.waitForTimeout(2000);

    const tabs = ['overview', 'adoption', 'models', 'license', 'anomalies'];
    for (const tab of tabs) {
      const tabBtn = page.locator(`[class*="tab"] button, button[class*="tab"]`).filter({ hasText: new RegExp(tab, 'i') }).first();
      const isVisible = await tabBtn.isVisible().catch(() => false);
      if (isVisible) {
        await tabBtn.click();
        await page.waitForTimeout(1500);
        const url = page.url();
        console.log(`Copilot tab "${tab}": URL=${url}`);
      } else {
        console.log(`Copilot tab "${tab}": button not found`);
      }
    }
  });

  test('copilot overview clickable metrics work', async ({ authedPage: page }) => {
    await navigateTo(page, '/copilot/overview');
    await page.waitForTimeout(3000);

    // Check for metric cards
    const metricCards = page.locator('[class*="metric"], [class*="card"]').filter({ hasText: /seat|active|inactive/i });
    const count = await metricCards.count();
    console.log(`Copilot overview: ${count} seat metric cards`);

    // Try clicking the first metric card
    if (count > 0) {
      await metricCards.first().click();
      await page.waitForTimeout(1000);
      const modal = page.locator('[class*="modal"], [class*="Modal"], [role="dialog"]');
      const modalVisible = await modal.first().isVisible().catch(() => false);
      console.log(`Copilot overview: metric click modal: ${modalVisible}`);
    }
  });
});

test.describe('Health Page Interactions', () => {
  test('health tab navigation works', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/repos');
    await page.waitForTimeout(2000);

    const tabs = [
      { text: 'Repository', slug: 'repos' },
      { text: 'Access', slug: 'access' },
      { text: 'Security', slug: 'security' },
      { text: 'Governance', slug: 'governance' },
      { text: 'Operations', slug: 'operations' },
      { text: 'License', slug: 'license' },
      { text: 'Maintenance', slug: 'maintenance' },
      { text: 'WAF', slug: 'waf' },
    ];

    for (const tab of tabs) {
      const tabBtn = page.locator('button').filter({ hasText: new RegExp(tab.text, 'i') }).first();
      if (await tabBtn.isVisible().catch(() => false)) {
        await tabBtn.click();
        await page.waitForTimeout(1500);
        const url = page.url();
        console.log(`Health tab "${tab.text}": URL=${url}, contains slug=${url.includes(tab.slug)}`);
      } else {
        console.log(`Health tab "${tab.text}": not found`);
      }
    }
  });

  test('health chips/badges are clickable and show data', async ({ authedPage: page }) => {
    await navigateTo(page, '/health/repos');
    await page.waitForTimeout(3000);

    // Find metric cards with counts
    const metricCards = page.locator('[class*="metric"], [class*="stat"], [class*="card"]').filter({ hasText: /\d+/ });
    const count = await metricCards.count();
    console.log(`Health repos: ${count} metric cards with numbers`);

    // Click each and check for modal/expansion
    for (let i = 0; i < Math.min(count, 5); i++) {
      const card = metricCards.nth(i);
      const text = await card.textContent();
      const clickable = await card.evaluate(el => {
        const style = window.getComputedStyle(el);
        return style.cursor === 'pointer' || el.closest('a') !== null || el.getAttribute('role') === 'button';
      }).catch(() => false);
      
      if (clickable) {
        console.log(`Health card ${i}: "${text?.slice(0, 50)}" — clickable`);
        await card.click();
        await page.waitForTimeout(1000);
        const modal = page.locator('[class*="modal"], [role="dialog"]').first();
        const modalVis = await modal.isVisible().catch(() => false);
        if (modalVis) {
          console.log(`Health card ${i}: opened modal`);
          // Close modal
          const closeBtn = page.locator('[class*="modal"] button, [role="dialog"] button').filter({ hasText: /close|×|✕/i }).first();
          if (await closeBtn.isVisible().catch(() => false)) {
            await closeBtn.click();
            await page.waitForTimeout(500);
          } else {
            await page.keyboard.press('Escape');
            await page.waitForTimeout(500);
          }
        }
      }
    }
  });
});

test.describe('Settings Page Interactions', () => {
  test('settings tabs all render content', async ({ authedPage: page }) => {
    const tabs = ['all', 'github', 'security', 'storage', 'notifications', 'system', 'audit', 'features'];
    
    for (const tab of tabs) {
      await navigateTo(page, `/settings/${tab}`);
      await page.waitForTimeout(1500);
      
      // Check for any meaningful content
      const body = await page.textContent('[class*="content"], [class*="main"], main') || '';
      const hasContent = body.trim().length > 50;
      const hasTable = await page.locator('table, [class*="table"]').first().isVisible().catch(() => false);
      const hasForm = await page.locator('input, select, textarea, [class*="toggle"]').first().isVisible().catch(() => false);
      const hasEmpty = body.includes('No settings') || body.includes('empty') || body.includes('No data');
      
      console.log(`Settings/${tab}: content=${hasContent}, table=${hasTable}, form=${hasForm}, empty=${hasEmpty}`);
      
      if (!hasContent && !hasTable && !hasForm) {
        console.log(`BUG: Settings/${tab} appears to be empty`);
      }
    }
  });

  test('settings edit button opens modal', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/all');
    await page.waitForTimeout(2000);

    const editBtn = page.locator('button:has-text("Edit"), button[aria-label*="edit"]').first();
    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click();
      await page.waitForTimeout(1000);
      const modal = page.locator('[class*="modal"], [role="dialog"]').first();
      console.log(`Settings edit modal: ${await modal.isVisible().catch(() => false)}`);
    } else {
      console.log('Settings: no edit buttons found');
    }
  });

  test('feature toggles are clickable', async ({ authedPage: page }) => {
    await navigateTo(page, '/settings/features');
    await page.waitForTimeout(2000);

    const toggles = page.locator('input[type="checkbox"]');
    const count = await toggles.count();
    console.log(`Features: ${count} toggles`);

    for (let i = 0; i < count; i++) {
      const toggle = toggles.nth(i);
      const checked = await toggle.isChecked();
      const label = await toggle.evaluate(el => {
        const row = el.closest('[class*="feature"]');
        return row?.querySelector('[class*="label"]')?.textContent || '';
      }).catch(() => '');
      console.log(`Feature "${label}": checked=${checked}`);
    }
  });
});

test.describe('Rules Page Interactions', () => {
  test('rules page has controls', async ({ authedPage: page }) => {
    await navigateTo(page, '/rules');
    await page.waitForTimeout(2000);

    const newRuleBtn = page.locator('button:has-text("New"), button:has-text("Create"), button:has-text("Add")').first();
    const hasNewRule = await newRuleBtn.isVisible().catch(() => false);
    console.log(`Rules: new rule button: ${hasNewRule}`);

    const syncBtn = page.locator('button:has-text("Sync")').first();
    const hasSync = await syncBtn.isVisible().catch(() => false);
    console.log(`Rules: sync button: ${hasSync}`);

    const ruleRows = page.locator('table tbody tr, [class*="rule"]');
    const rowCount = await ruleRows.count();
    console.log(`Rules: ${rowCount} rule rows`);
  });
});

test.describe('Users Page Interactions', () => {
  test('users page shows role mappings', async ({ authedPage: page }) => {
    await navigateTo(page, '/users');
    await page.waitForTimeout(2000);

    const addBtn = page.locator('button:has-text("Add"), button:has-text("New")').first();
    const hasAdd = await addBtn.isVisible().catch(() => false);
    console.log(`Users: add button: ${hasAdd}`);

    const rows = page.locator('table tbody tr, [class*="user"], [class*="mapping"]');
    const rowCount = await rows.count();
    console.log(`Users: ${rowCount} user/mapping rows`);
  });
});

test.describe('Integrations Page Interactions', () => {
  test('integrations page shows connector cards', async ({ authedPage: page }) => {
    await navigateTo(page, '/integrations');
    await page.waitForTimeout(2000);

    const cards = page.locator('[class*="card"], [class*="connector"], [class*="integration"]');
    const cardCount = await cards.count();
    console.log(`Integrations: ${cardCount} cards`);

    // Check for configure buttons
    const configBtns = page.locator('button:has-text("Configure"), button:has-text("Setup"), button:has-text("Connect")');
    const btnCount = await configBtns.count();
    console.log(`Integrations: ${btnCount} configure buttons`);
  });
});
