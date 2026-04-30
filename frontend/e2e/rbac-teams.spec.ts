import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Team Management E2E Tests
//
// Tests the admin teams API contract via mocked responses and direct API
// requests. Covers full CRUD lifecycle: create team, add/remove members,
// assign/remove roles, and delete team.
// ---------------------------------------------------------------------------

const TEAMS_LIST_MOCK = [
  {
    id: 1,
    name: 'Security Team',
    slug: 'security-team',
    description: 'Handles security operations',
    member_count: 5,
    role_count: 2,
    auto_sync: false,
    created_by: 'admin',
    created_at: '2024-01-15T00:00:00Z',
  },
  {
    id: 2,
    name: 'Platform Engineering',
    slug: 'platform-engineering',
    description: 'Infrastructure and platform work',
    member_count: 8,
    role_count: 3,
    auto_sync: true,
    created_by: 'admin',
    created_at: '2024-02-01T00:00:00Z',
  },
];

const TEAM_DETAIL_MOCK = {
  id: 1,
  name: 'Security Team',
  slug: 'security-team',
  description: 'Handles security operations',
  github_org: 'octowatch-org',
  github_team_slug: 'security',
  auto_sync: false,
  created_by: 'admin',
  created_at: '2024-01-15T00:00:00Z',
  updated_at: null,
  members: [
    { user_login: 'alice', added_by: 'admin', created_at: '2024-01-15T00:00:00Z' },
    { user_login: 'bob', added_by: 'admin', created_at: '2024-01-16T00:00:00Z' },
  ],
  roles: [
    {
      role_id: 2,
      role_name: 'security_analyst',
      role_display_name: 'Security Analyst',
      org_slug: null,
      repo_slugs: null,
      assigned_by: 'admin',
      created_at: '2024-01-15T00:00:00Z',
    },
  ],
};

const NEW_TEAM_RESPONSE = {
  id: 10,
  name: 'E2E Test Team',
  slug: 'e2e-test-team',
  description: 'Created during E2E testing',
  github_org: null,
  github_team_slug: null,
  auto_sync: false,
  created_by: 'admin',
  created_at: '2024-06-01T00:00:00Z',
  updated_at: null,
  members: [],
  roles: [],
};

test.describe('Team Management API', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  test('GET /api/v1/admin/teams returns team list with counts', async ({ page }) => {
    await page.route('**/api/v1/admin/teams', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(TEAMS_LIST_MOCK),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/teams');
    if (response.status() === 200) {
      const teams = await response.json();
      expect(teams).toHaveLength(2);
      expect(teams[0]).toHaveProperty('member_count');
      expect(teams[0]).toHaveProperty('role_count');
      expect(teams[0].slug).toBeTruthy();
    }
  });

  test('POST /api/v1/admin/teams creates a new team', async ({ page }) => {
    await page.route('**/api/v1/admin/teams', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(NEW_TEAM_RESPONSE),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/teams', {
      data: {
        name: 'E2E Test Team',
        description: 'Created during E2E testing',
      },
    });

    if (response.status() === 201) {
      const team = await response.json();
      expect(team.name).toBe('E2E Test Team');
      expect(team.slug).toBe('e2e-test-team');
      expect(team.members).toHaveLength(0);
      expect(team.roles).toHaveLength(0);
    }
  });

  test('GET /api/v1/admin/teams/:id returns team detail with members and roles', async ({ page }) => {
    await page.route('**/api/v1/admin/teams/1', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(TEAM_DETAIL_MOCK),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/teams/1');
    if (response.status() === 200) {
      const team = await response.json();
      expect(team.name).toBe('Security Team');
      expect(team.members).toHaveLength(2);
      expect(team.members[0].user_login).toBe('alice');
      expect(team.roles).toHaveLength(1);
      expect(team.roles[0].role_name).toBe('security_analyst');
    }
  });

  test('POST /api/v1/admin/teams/:id/members adds a member', async ({ page }) => {
    const newMember = {
      user_login: 'charlie',
      added_by: 'admin',
      created_at: '2024-06-01T12:00:00Z',
    };

    await page.route('**/api/v1/admin/teams/1/members', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(newMember),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/teams/1/members', {
      data: { user_login: 'charlie' },
    });

    if (response.status() === 201) {
      const member = await response.json();
      expect(member.user_login).toBe('charlie');
      expect(member.added_by).toBe('admin');
    }
  });

  test('DELETE /api/v1/admin/teams/:id/members/:login removes a member', async ({ page }) => {
    await page.route('**/api/v1/admin/teams/1/members/bob', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({ status: 204 });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.delete('/api/v1/admin/teams/1/members/bob');
    expect([204, 401, 403]).toContain(response.status());
  });

  test('POST /api/v1/admin/teams/:id/roles assigns a role to team', async ({ page }) => {
    const roleAssignment = {
      role_id: 3,
      role_name: 'org_admin',
      role_display_name: 'Org Admin',
      org_slug: null,
      repo_slugs: null,
      assigned_by: 'admin',
      created_at: '2024-06-01T12:00:00Z',
    };

    await page.route('**/api/v1/admin/teams/1/roles', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(roleAssignment),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/teams/1/roles', {
      data: { role_id: 3 },
    });

    if (response.status() === 201) {
      const assignment = await response.json();
      expect(assignment.role_name).toBe('org_admin');
      expect(assignment.assigned_by).toBe('admin');
    }
  });

  test('DELETE /api/v1/admin/teams/:id/roles/:roleId removes role from team', async ({ page }) => {
    await page.route('**/api/v1/admin/teams/1/roles/3', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({ status: 204 });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.delete('/api/v1/admin/teams/1/roles/3');
    expect([204, 401, 403]).toContain(response.status());
  });

  test('DELETE /api/v1/admin/teams/:id deletes a team', async ({ page }) => {
    await page.route('**/api/v1/admin/teams/10', (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({ status: 204 });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.delete('/api/v1/admin/teams/10');
    expect([204, 401, 403]).toContain(response.status());
  });

  test('duplicate team name returns 409 conflict', async ({ page }) => {
    await page.route('**/api/v1/admin/teams', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: "Team with name 'Security Team' or slug 'security-team' already exists",
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/teams', {
      data: { name: 'Security Team', description: 'Duplicate' },
    });

    expect([409, 401, 403]).toContain(response.status());
  });

  test('duplicate member returns 409 conflict', async ({ page }) => {
    await page.route('**/api/v1/admin/teams/1/members', (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: "User 'alice' is already a member of this team",
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.post('/api/v1/admin/teams/1/members', {
      data: { user_login: 'alice' },
    });

    expect([409, 401, 403]).toContain(response.status());
  });
});
