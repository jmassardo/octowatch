import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Sidebar navigation tests — click each nav link and verify routing.
//
// Authentication is handled by the "setup" project in playwright.config.ts.
// ---------------------------------------------------------------------------

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
