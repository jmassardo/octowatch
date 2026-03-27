import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Sidebar navigation tests — click each nav link and verify routing.
//
// These tests require an authenticated session because the sidebar is only
// rendered inside the AuthGuard-protected AppShell.
//
// TODO: Configure authenticated storageState for these tests:
//   1. Create e2e/auth.setup.ts that logs in and saves session state
//   2. Add a "setup" project to playwright.config.ts
//   3. Uncomment the `test.use(...)` line below
//
// Until auth is configured, these tests will be redirected to /login and
// will not find the sidebar.  They are structured so that enabling auth is
// a single-line change.
// ---------------------------------------------------------------------------

// TODO: Uncomment when auth setup is available
// test.use({ storageState: 'e2e/.auth/user.json' });

const navItems = [
  { label: 'Dashboard', path: '/dashboard', heading: 'Dashboard' },
  {
    label: 'Threat Detections',
    path: '/threats',
    heading: 'Threat Detections',
  },
  { label: 'Events Explorer', path: '/events', heading: 'Events Explorer' },
  {
    label: 'Engineering Velocity',
    path: '/velocity',
    heading: 'Engineering Velocity',
  },
  {
    label: 'Developer Activity',
    path: '/devactivity',
    heading: 'Developer Activity',
  },
  { label: 'Copilot Insights', path: '/copilot', heading: 'Copilot Insights' },
  { label: 'Reports', path: '/reports', heading: 'Reports' },
  { label: 'Query Explorer', path: '/query', heading: 'Query Explorer' },
  { label: 'Detection Rules', path: '/rules', heading: 'Detection Rules' },
  { label: 'Users & Roles', path: '/users', heading: 'Users' },
  { label: 'Integrations', path: '/integrations', heading: 'Integrations' },
];

test.describe('Sidebar navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
  });

  for (const { label, path, heading } of navItems) {
    test(`navigates to ${path} via "${label}" link`, async ({ page }) => {
      const sidebar = page.getByRole('navigation', {
        name: 'Main navigation',
      });
      await sidebar.getByRole('link', { name: label }).click();

      await expect(page).toHaveURL(new RegExp(`${path}$`));
      await expect(
        page.getByRole('heading', { name: heading }),
      ).toBeVisible();
    });
  }
});
