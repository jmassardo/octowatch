import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Smoke tests — verify every route is reachable and the app renders.
//
// Authentication is handled by the "setup" project in playwright.config.ts
// which runs auth.setup.ts to create a session state file.
// ---------------------------------------------------------------------------

test.describe('Login page', () => {
  test('renders with sign-in options', async ({ page }) => {
    // Clear auth state for this test to see login page
    await page.context().clearCookies();
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

test.describe('Setup page', () => {
  test('renders the setup wizard', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/setup');

    await expect(
      page.getByRole('heading', { name: /octowatch setup/i }),
    ).toBeVisible();
  });
});

test.describe('Protected routes (authenticated)', () => {
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
    test(`${route.path} → renders ${route.expectedTitle}`, async ({
      page,
    }) => {
      await page.goto(route.path);

      // Should NOT redirect to login when authenticated
      await expect(page).not.toHaveURL(/\/login/);
      await expect(
        page.getByRole('heading', { name: route.expectedTitle }),
      ).toBeVisible({ timeout: 10_000 });
    });
  }
});
