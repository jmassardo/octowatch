import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Smoke tests — verify every route is reachable and the app renders.
//
// The OctoWatch app wraps all feature routes in an AuthGuard that redirects
// unauthenticated users to /login.  Until an authenticated storageState is
// configured these tests verify the redirect-to-login behaviour for each
// protected route and that the login page itself renders correctly.
//
// TODO: Add authenticated smoke tests using Playwright's storageState.
// See: https://playwright.dev/docs/auth
//
// To enable authenticated tests:
//   1. Create e2e/auth.setup.ts that logs in and saves session state
//   2. Add a "setup" project to playwright.config.ts
//   3. Use `test.use({ storageState: 'e2e/.auth/user.json' })` below
//   4. Replace login-redirect assertions with actual page title checks
// ---------------------------------------------------------------------------

test.describe('Login page', () => {
  test('renders with sign-in options', async ({ page }) => {
    await page.goto('/login');

    await expect(
      page.getByRole('heading', { name: 'OctoWatch' }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /sign in with github/i }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /sign in with saml/i }),
    ).toBeVisible();
  });
});

test.describe('Protected routes (unauthenticated)', () => {
  // Every protected route should redirect to /login when the user has no
  // active session.  The `expectedTitle` field documents what heading each
  // page should show once authenticated tests are in place.
  const protectedRoutes = [
    { path: '/dashboard', expectedTitle: 'Dashboard' },
    { path: '/threats', expectedTitle: 'Threat Detections' },
    { path: '/events', expectedTitle: 'Events Explorer' },
    { path: '/velocity', expectedTitle: 'Engineering Velocity' },
    { path: '/devactivity', expectedTitle: 'Developer Activity' },
    { path: '/copilot', expectedTitle: 'Copilot Insights' },
    { path: '/reports', expectedTitle: 'Reports' },
    { path: '/query', expectedTitle: 'Query Explorer' },
    { path: '/rules', expectedTitle: 'Detection Rules' },
    { path: '/users', expectedTitle: 'Users' },
    { path: '/integrations', expectedTitle: 'Integrations' },
  ];

  for (const route of protectedRoutes) {
    test(`${route.path} → redirects to login`, async ({ page }) => {
      await page.goto(route.path);

      await expect(page).toHaveURL(/\/login/);
      await expect(
        page.getByRole('heading', { name: 'OctoWatch' }),
      ).toBeVisible();
    });
  }
});
