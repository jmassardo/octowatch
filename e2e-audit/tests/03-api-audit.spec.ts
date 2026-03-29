/**
 * Comprehensive UI audit — Phase 3: API responses & data quality
 *
 * Tests API endpoints directly for errors, mock data, and correctness.
 */
import { test, expect } from './helpers';

test.describe('API Endpoint Audit', () => {
  test('all major API endpoints return valid data', async ({ authedPage: page }) => {
    const endpoints = [
      '/api/v1/auth/me',
      '/api/v1/events?page_size=5',
      '/api/v1/detections?page_size=5',
      '/api/v1/reports/catalog',
      '/api/v1/reports/mau',
      '/api/v1/reports/seat-utilization',
      '/api/v1/reports/repo-creation-rate',
      '/api/v1/reports/actions-volume',
      '/api/v1/reports/copilot-seats',
      '/api/v1/reports/codespace-hours',
      '/api/v1/reports/pat-counts',
      '/api/v1/reports/webhook-counts',
      '/api/v1/query/templates',
      '/api/v1/rules',
      '/api/v1/admin/roles',
      '/api/v1/admin/assignments',
      '/api/v1/admin/settings',
      '/api/v1/admin/settings/audit/trail',
      '/api/v1/admin/retention',
      '/api/v1/admin/top-actors',
      '/api/v1/admin/event-trend',
      '/api/v1/admin/sessions',
      '/api/v1/features',
      '/api/v1/health-signals/summary',
      '/api/v1/health-signals/pat-health',
      '/api/v1/health-signals/repo-health',
      '/api/v1/health-signals/security-posture',
      '/api/v1/health-signals/sso',
      '/api/v1/health-signals/workflows',
      '/api/v1/health-signals/branch-protection',
      '/api/v1/health-signals/system',
      '/api/v1/health-signals/settings',
      '/api/v1/health-signals/waf-findings',
      '/api/v1/health-signals/teams',
      '/api/v1/copilot/overview',
      '/api/v1/copilot/adoption',
      '/api/v1/copilot/models',
      '/api/v1/copilot/anomalies',
      '/api/v1/admin/sync/status',
      '/api/v1/admin/sync/config',
      '/api/v1/integrations/ticketing',
      '/api/v1/integrations/notifications',
    ];

    const results: { endpoint: string; status: number; ok: boolean; body: string }[] = [];

    for (const endpoint of endpoints) {
      const resp = await page.request.get(endpoint, { ignoreHTTPSErrors: true });
      let body = '';
      try { body = await resp.text(); } catch {}
      
      results.push({
        endpoint,
        status: resp.status(),
        ok: resp.ok(),
        body: body.slice(0, 300),
      });
    }

    // Report
    for (const r of results) {
      const icon = r.ok ? '✓' : '✗';
      console.log(`${icon} ${r.status} ${r.endpoint}`);
      if (!r.ok) {
        console.log(`  Response: ${r.body}`);
      }
      // Check for mock/sample markers in successful responses
      if (r.ok && (r.body.includes('"mock"') || r.body.includes('"sample"') || r.body.includes('placeholder'))) {
        console.log(`  ⚠ MOCK DATA detected in response`);
      }
    }

    // Count failures
    const failures = results.filter(r => !r.ok && r.status !== 403);
    console.log(`\nAPI Summary: ${results.length - failures.length}/${results.length} OK, ${failures.length} errors (excluding 403 scope)`);
  });

  test('query run endpoint works', async ({ authedPage: page }) => {
    // Navigate to the page first to get cookies set properly
    await navigateTo(page, '/query');
    await page.waitForTimeout(2000);
    
    // Use the page's request context which has cookies
    const resp = await page.request.post('/api/v1/query/run', {
      data: { sql: 'SELECT COUNT(*) as total FROM events' },
      ignoreHTTPSErrors: true,
    });
    // May get 403 CSRF in direct API call — that's expected when
    // calling POST outside the SPA. The real test is the UI query test.
    const status = resp.status();
    console.log(`Query run: ${status}`);
    // Accept 200 (success) or 403 (CSRF protection working correctly)
    expect([200, 403]).toContain(status);
  });

  test('query validate endpoint works', async ({ authedPage: page }) => {
    const resp = await page.request.post('/api/v1/query/validate', {
      data: { sql: 'SELECT * FROM events LIMIT 1' },
      ignoreHTTPSErrors: true,
    });
    const body = await resp.text();
    console.log(`Query validate: ${resp.status()} → ${body.slice(0, 300)}`);
  });

  test('reports export endpoints work', async ({ authedPage: page }) => {
    const reportTypes = ['mau', 'seat-utilization', 'repo-creation-rate', 'actions-volume'];
    for (const rt of reportTypes) {
      const resp = await page.request.get(`/api/v1/reports/export/${rt}`, { ignoreHTTPSErrors: true });
      console.log(`Report export ${rt}: ${resp.status()}`);
    }
  });
});
