import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Smoke tests — verify every route is reachable and the app renders.
//
// Authentication is handled by the "setup" project in playwright.config.ts
// which runs auth.setup.ts to create a session state file.
//
// NOTE: Page titles are rendered as <h1>/<h2> elements on some pages and as
// styled <div> elements on others.  Assertions are scoped to the <main>
// content area so they never accidentally match sidebar navigation labels.
// ---------------------------------------------------------------------------

test.describe('Login page', () => {
  test('renders with sign-in options', async ({ page }) => {
    // Clear auth state for this test to see login page
    await page.context().clearCookies();
    await page.goto('/login');

    await expect(page.getByRole('heading', { name: 'OctoWatch' })).toBeVisible();
    await expect(page.getByRole('link', { name: /sign in with github/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /sign in with saml/i })).toBeVisible();
  });
});

test.describe('Setup page', () => {
  test('renders the setup wizard', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/setup');

    await expect(page.getByRole('heading', { name: /octowatch setup/i })).toBeVisible();
  });
});

// Protected route tests require auth cookies to persist through self-signed
// TLS in CI. Marking as fixme until proper TLS is configured.
// See: https://github.com/microsoft/playwright/issues/35206
test.describe('Protected routes (authenticated)', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');
  // Each route is tested by navigating directly (no sidebar interaction), so
  // feature-gated pages still render — they show a "disabled" message instead
  // of the full UI, but the title text remains visible.
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
    { path: '/settings', expectedTitle: 'Settings' },
    { path: '/posture', expectedTitle: 'Security Posture' },
    { path: '/crossorg', expectedTitle: 'Cross-Organization' },
    { path: '/workflows', expectedTitle: 'Workflow Security' },
    { path: '/advanced-security', expectedTitle: 'Advanced Security' },
    { path: '/health', expectedTitle: 'Org Health' },
  ];

  for (const route of protectedRoutes) {
    test(`${route.path} → renders ${route.expectedTitle}`, async ({ page }) => {
      await page.goto(route.path);

      // Should NOT redirect to login when authenticated
      await expect(page).not.toHaveURL(/\/login/);

      // Page titles may be heading elements (h1/h2) or styled divs.
      // Scope to <main> to avoid matching the sidebar navigation labels.
      const main = page.locator('main');
      await expect(main.getByText(route.expectedTitle).first()).toBeVisible({ timeout: 10_000 });
    });
  }

  test('/health → redirects to /health/repos', async ({ page }) => {
    await page.goto('/health');
    await expect(page).toHaveURL(/\/health\/repos/);
  });

  test('/integrations → redirects to /settings/integrations', async ({ page }) => {
    await page.goto('/integrations');
    await expect(page).toHaveURL(/\/settings\/integrations/);
  });

  test('/actors/test-user → renders actor profile or 404', async ({ page }) => {
    await page.goto('/actors/test-user');
    await expect(page).not.toHaveURL(/\/login/);

    // The actor may not exist — accept either a profile heading or
    // a "not found" / error state.  Both prove the route is reachable.
    const main = page.locator('main');
    const profileHeading = main.getByText('@test-user');
    const notFound = main.getByText(/not found|no actor|error/i);
    await expect(profileHeading.or(notFound).first()).toBeVisible({
      timeout: 10_000,
    });
  });
});
