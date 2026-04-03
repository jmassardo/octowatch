import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Sidebar navigation tests — click each nav link and verify routing.
//
// Authentication is handled by the "setup" project in playwright.config.ts.
//
// Only "always-visible" sidebar items are included.  Feature-gated items
// (Engineering Velocity, Developer Activity, Copilot Insights, Org Health)
// depend on backend configuration and are covered by the smoke tests which
// navigate directly to their routes.
// ---------------------------------------------------------------------------

const navItems = [
  { label: 'Dashboard', path: '/dashboard', heading: 'Dashboard' },
  {
    label: 'Threat Detections',
    path: '/threats',
    heading: 'Threat Detections',
  },
  { label: 'Events Explorer', path: '/events', heading: 'Events Explorer' },
  { label: 'Reports', path: '/reports', heading: 'Reports' },
  { label: 'Query Explorer', path: '/query', heading: 'Query Explorer' },
  { label: 'Detection Rules', path: '/rules', heading: 'Detection Rules' },
  { label: 'Users & Roles', path: '/users', heading: 'Users' },
  // Settings link navigates to /settings which redirects to /settings/all
  { label: 'Settings', path: '/settings/all', heading: 'Settings' },
];

// Navigation tests require auth cookies to persist through self-signed
// TLS in CI. Marking as fixme until proper TLS is configured.
test.describe('Sidebar navigation', () => {
  test.fixme(
    !!process.env.CI,
    'Auth cookies do not persist through self-signed TLS in CI',
  );
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

      // Page titles may be heading elements (h1/h2) or styled divs.
      // Scope to <main> to avoid matching the sidebar navigation labels.
      const main = page.locator('main');
      await expect(
        main.getByText(heading).first(),
      ).toBeVisible();
    });
  }
});
