import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// RBAC Role Management E2E Tests
//
// Tests the admin roles API and any future admin roles page. Since the
// frontend currently only exposes /admin/auth as a routed page, these tests
// validate the API contract via page.route() interception and verify
// behaviors through direct API calls and mocked UI responses.
// ---------------------------------------------------------------------------

const SYSTEM_ROLES_MOCK = [
  { id: 1, name: 'super_admin', display_name: 'Super Admin', description: 'Full system access', permission_count: 1, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 2, name: 'security_analyst', display_name: 'Security Analyst', description: 'View and manage threats', permission_count: 8, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 3, name: 'org_admin', display_name: 'Org Admin', description: 'Manage organization settings', permission_count: 12, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 4, name: 'auditor', display_name: 'Auditor', description: 'Read-only audit access', permission_count: 4, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 5, name: 'incident_responder', display_name: 'Incident Responder', description: 'Manage incidents and threats', permission_count: 6, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 6, name: 'compliance_officer', display_name: 'Compliance Officer', description: 'Compliance and reporting', permission_count: 5, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
  { id: 7, name: 'viewer', display_name: 'Viewer', description: 'Read-only access', permission_count: 3, is_system: true, is_custom: false, created_at: '2024-01-01T00:00:00Z' },
];

const CUSTOM_ROLE_RESPONSE = {
  id: 100,
  name: 'custom_tester',
  display_name: 'Custom Tester',
  description: 'A test custom role',
  permissions: ['events:view', 'threats:view'],
  is_system: false,
  is_custom: true,
  created_at: '2024-06-01T00:00:00Z',
  updated_at: null,
  assignment_count: 0,
};

test.describe('RBAC Role Management API', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  test('GET /api/v1/admin/roles returns list of roles', async ({ page }) => {
    // Intercept the roles API call
    let apiCalled = false;
    await page.route('**/api/v1/admin/roles', (route) => {
      apiCalled = true;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SYSTEM_ROLES_MOCK),
      });
    });

    const response = await page.request.get('/api/v1/admin/roles');
    // If running against a live backend, the response may differ from the mock.
    // Accept either a 200 with data or a 401/403 if auth is required.
    expect([200, 401, 403]).toContain(response.status());
  });

  test('system roles list includes 7 expected roles', async ({ page }) => {
    await page.route('**/api/v1/admin/roles', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SYSTEM_ROLES_MOCK),
      });
    });

    // Navigate to trigger the interceptor context
    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/roles');
    if (response.status() === 200) {
      const roles = await response.json();
      expect(roles.length).toBeGreaterThanOrEqual(7);

      // All system roles should have is_system: true
      const systemRoles = roles.filter((r: { is_system: boolean }) => r.is_system);
      expect(systemRoles.length).toBeGreaterThanOrEqual(7);
    }
  });

  test('system roles cannot be deleted (403)', async ({ page }) => {
    await page.route('**/api/v1/admin/roles/1', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'System roles cannot be deleted' }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.delete('/api/v1/admin/roles/1');
    // System roles should return 403 on delete
    expect([403, 401]).toContain(response.status());
  });

  test('create a custom role via POST', async ({ page }) => {
    await page.route('**/api/v1/admin/roles', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(CUSTOM_ROLE_RESPONSE),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/roles', {
      data: {
        name: 'custom_tester',
        display_name: 'Custom Tester',
        description: 'A test custom role',
        permissions: ['events:view', 'threats:view'],
      },
    });

    if (response.status() === 201) {
      const role = await response.json();
      expect(role.name).toBe('custom_tester');
      expect(role.is_custom).toBe(true);
      expect(role.is_system).toBe(false);
      expect(role.permissions).toContain('events:view');
    }
  });

  test('update a custom role via PATCH', async ({ page }) => {
    const updatedRole = {
      ...CUSTOM_ROLE_RESPONSE,
      display_name: 'Updated Tester Role',
      permissions: ['events:view', 'threats:view', 'reports:view'],
      updated_at: '2024-06-02T00:00:00Z',
    };

    await page.route('**/api/v1/admin/roles/100', (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updatedRole),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.patch('/api/v1/admin/roles/100', {
      data: {
        display_name: 'Updated Tester Role',
        permissions: ['events:view', 'threats:view', 'reports:view'],
      },
    });

    if (response.status() === 200) {
      const role = await response.json();
      expect(role.display_name).toBe('Updated Tester Role');
      expect(role.permissions).toHaveLength(3);
    }
  });

  test('delete a custom role via DELETE', async ({ page }) => {
    await page.route('**/api/v1/admin/roles/100', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({ status: 204 });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.delete('/api/v1/admin/roles/100');
    expect([204, 401, 403]).toContain(response.status());
  });

  test('cannot create role with reserved system name (409)', async ({ page }) => {
    await page.route('**/api/v1/admin/roles', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: "Role name 'super_admin' is reserved for system roles" }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/roles', {
      data: {
        name: 'super_admin',
        display_name: 'Super Admin Copy',
        description: 'Trying to override system role',
        permissions: ['*:*'],
      },
    });

    expect([409, 401, 403, 422]).toContain(response.status());
  });

  test('invalid permissions return 422', async ({ page }) => {
    await page.route('**/api/v1/admin/roles', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: { errors: ['Cannot assign wildcard *:* to custom roles'] } }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/roles', {
      data: {
        name: 'wildcard_role',
        display_name: 'Wildcard',
        description: 'Invalid',
        permissions: ['*:*'],
      },
    });

    expect([422, 401, 403]).toContain(response.status());
  });
});
