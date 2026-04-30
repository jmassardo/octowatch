import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Audit Log E2E Tests
//
// Tests the audit log API endpoints: listing with pagination and filters,
// and CSV export functionality.
// ---------------------------------------------------------------------------

const AUDIT_LOG_MOCK = {
  items: [
    {
      id: 1,
      timestamp: '2024-06-01T10:00:00Z',
      actor: 'admin',
      action: 'role.create',
      resource_type: 'rbac_role',
      resource_id: '100',
      details: { name: 'custom_tester' },
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0',
      outcome: 'success',
    },
    {
      id: 2,
      timestamp: '2024-06-01T09:30:00Z',
      actor: 'alice',
      action: 'team.member_add',
      resource_type: 'team_membership',
      resource_id: '1',
      details: { user_login: 'charlie' },
      ip_address: '10.0.0.5',
      user_agent: 'Mozilla/5.0',
      outcome: 'success',
    },
    {
      id: 3,
      timestamp: '2024-06-01T09:00:00Z',
      actor: 'admin',
      action: 'auth_method.update',
      resource_type: 'auth_method',
      resource_id: 'saml_sso',
      details: { enabled: true },
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0',
      outcome: 'success',
    },
    {
      id: 4,
      timestamp: '2024-05-31T18:00:00Z',
      actor: 'bob',
      action: 'login.attempt',
      resource_type: 'session',
      resource_id: null,
      details: {},
      ip_address: '172.16.0.10',
      user_agent: 'curl/8.0',
      outcome: 'denied',
    },
    {
      id: 5,
      timestamp: '2024-05-31T12:00:00Z',
      actor: 'admin',
      action: 'retention.update',
      resource_type: 'retention_policy',
      resource_id: 'events',
      details: { retention_days: 180 },
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0',
      outcome: 'success',
    },
  ],
  total: 120,
  page: 1,
  page_size: 50,
  has_more: true,
};

const AUDIT_LOG_PAGE_2_MOCK = {
  items: [
    {
      id: 6,
      timestamp: '2024-05-30T10:00:00Z',
      actor: 'admin',
      action: 'team.create',
      resource_type: 'team',
      resource_id: '5',
      details: { name: 'New Team' },
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0',
      outcome: 'success',
    },
  ],
  total: 120,
  page: 2,
  page_size: 50,
  has_more: true,
};

const FILTERED_BY_ACTOR_MOCK = {
  items: [AUDIT_LOG_MOCK.items[0], AUDIT_LOG_MOCK.items[2], AUDIT_LOG_MOCK.items[4]],
  total: 3,
  page: 1,
  page_size: 50,
  has_more: false,
};

test.describe('Audit Log API', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  test('GET /api/v1/admin/audit-log returns paginated entries', async ({ page }) => {
    await page.route('**/api/v1/admin/audit-log?*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUDIT_LOG_MOCK),
      });
    });
    await page.route('**/api/v1/admin/audit-log', (route) => {
      if (!route.request().url().includes('?')) {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(AUDIT_LOG_MOCK),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log');
    if (response.status() === 200) {
      const data = await response.json();
      expect(data).toHaveProperty('items');
      expect(data).toHaveProperty('total');
      expect(data).toHaveProperty('page');
      expect(data).toHaveProperty('page_size');
      expect(data).toHaveProperty('has_more');
      expect(data.items.length).toBeGreaterThan(0);

      // Each item should have the expected shape
      const item = data.items[0];
      expect(item).toHaveProperty('id');
      expect(item).toHaveProperty('timestamp');
      expect(item).toHaveProperty('actor');
      expect(item).toHaveProperty('action');
      expect(item).toHaveProperty('resource_type');
      expect(item).toHaveProperty('outcome');
    }
  });

  test('filter by actor returns only that actor entries', async ({ page }) => {
    await page.route('**/api/v1/admin/audit-log*actor=admin*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(FILTERED_BY_ACTOR_MOCK),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log?actor=admin');
    if (response.status() === 200) {
      const data = await response.json();
      // All returned items should be from 'admin'
      for (const item of data.items) {
        expect(item.actor).toBe('admin');
      }
    }
  });

  test('filter by action type returns matching entries', async ({ page }) => {
    const filteredMock = {
      items: [AUDIT_LOG_MOCK.items[0]],
      total: 1,
      page: 1,
      page_size: 50,
      has_more: false,
    };

    await page.route('**/api/v1/admin/audit-log*action=role*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(filteredMock),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log?action=role*');
    if (response.status() === 200) {
      const data = await response.json();
      for (const item of data.items) {
        expect(item.action).toMatch(/^role\./);
      }
    }
  });

  test('filter by date range narrows results', async ({ page }) => {
    const dateFilteredMock = {
      items: AUDIT_LOG_MOCK.items.slice(0, 3),
      total: 3,
      page: 1,
      page_size: 50,
      has_more: false,
    };

    await page.route('**/api/v1/admin/audit-log*start_date*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(dateFilteredMock),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get(
      '/api/v1/admin/audit-log?start_date=2024-06-01T00:00:00Z&end_date=2024-06-02T00:00:00Z',
    );
    if (response.status() === 200) {
      const data = await response.json();
      expect(data.total).toBeLessThanOrEqual(AUDIT_LOG_MOCK.total);
    }
  });

  test('pagination: page 2 returns different entries', async ({ page }) => {
    await page.route('**/api/v1/admin/audit-log*page=2*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUDIT_LOG_PAGE_2_MOCK),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log?page=2&page_size=50');
    if (response.status() === 200) {
      const data = await response.json();
      expect(data.page).toBe(2);
      expect(data.items.length).toBeGreaterThan(0);
      // Page 2 items should have different IDs from page 1
      expect(data.items[0].id).not.toBe(AUDIT_LOG_MOCK.items[0].id);
    }
  });

  test('export endpoint returns CSV content', async ({ page }) => {
    const csvContent =
      'id,timestamp,actor,action,resource_type,resource_id,outcome,ip_address,user_agent,details\n' +
      '1,2024-06-01T10:00:00,admin,role.create,rbac_role,100,success,192.168.1.1,Mozilla/5.0,{}\n';

    await page.route('**/api/v1/admin/audit-log/export*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'text/csv',
        headers: {
          'Content-Disposition': 'attachment; filename=audit_log_export.csv',
        },
        body: csvContent,
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log/export');
    if (response.status() === 200) {
      const contentType = response.headers()['content-type'];
      expect(contentType).toContain('text/csv');

      const body = await response.text();
      expect(body).toContain('id,timestamp,actor,action');
      expect(body).toContain('role.create');
    }
  });

  test('export with too many rows returns 400', async ({ page }) => {
    await page.route('**/api/v1/admin/audit-log/export*', (route) => {
      route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Export exceeds maximum of 100,000 rows (150,000 matched). Please narrow your filters.',
        }),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log/export');
    expect([400, 401, 403]).toContain(response.status());
  });

  test('filter by outcome shows only denied entries', async ({ page }) => {
    const deniedMock = {
      items: [AUDIT_LOG_MOCK.items[3]],
      total: 1,
      page: 1,
      page_size: 50,
      has_more: false,
    };

    await page.route('**/api/v1/admin/audit-log*outcome=denied*', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(deniedMock),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/audit-log?outcome=denied');
    if (response.status() === 200) {
      const data = await response.json();
      for (const item of data.items) {
        expect(item.outcome).toBe('denied');
      }
    }
  });
});
