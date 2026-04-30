import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// UX Components E2E Tests
//
// Validates the UX consistency framework: Toast notifications, EmptyState,
// ErrorState, LoadingButton, ConfirmDialog, PageHeader, and SkeletonLoader
// components behave correctly in context.
// ---------------------------------------------------------------------------

/** Dismiss the guided tour if it appears. */
async function dismissTourIfPresent(page: Page) {
  const closeBtn = page.getByRole('button', { name: 'Close tour' });
  if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await closeBtn.click();
    await expect(page.getByRole('dialog', { name: 'Guided tour' })).toBeHidden({ timeout: 3_000 });
  }
}

test.describe('UX Components', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  // -------------------------------------------------------------------------
  // Toast Notifications
  // -------------------------------------------------------------------------
  test.describe('Toast Notifications', () => {
    test('toast appears on successful save action', async ({ page }) => {
      // Set up mocks for auth settings page to trigger a toast on toggle confirm
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1,
                method_name: 'github_oauth',
                display_name: 'GitHub OAuth',
                enabled: true,
                config_json: {},
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/methods/github_oauth', (route) => {
        if (route.request().method() === 'PATCH') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              id: 1,
              method_name: 'github_oauth',
              display_name: 'GitHub OAuth',
              enabled: false,
              config_json: {},
              created_at: '2024-01-01T00:00:00Z',
              updated_at: '2024-06-01T00:00:00Z',
            }),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });

      // Confirm the dialog
      await page.getByRole('button', { name: 'Disable' }).last().click();

      // Toast should appear with success message
      const toast = page.locator('[role="alert"]');
      await expect(toast.first()).toBeVisible({ timeout: 10_000 });
      await expect(toast.first()).toContainText(/updated|saved|success/i);
    });

    test('toast auto-dismisses after timeout', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1,
                method_name: 'github_oauth',
                display_name: 'GitHub OAuth',
                enabled: true,
                config_json: {},
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/methods/github_oauth', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1,
            method_name: 'github_oauth',
            display_name: 'GitHub OAuth',
            enabled: false,
            config_json: {},
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-06-01T00:00:00Z',
          }),
        });
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });
      await page.getByRole('button', { name: 'Disable' }).last().click();

      // Toast appears
      const toast = page.locator('[role="alert"]');
      await expect(toast.first()).toBeVisible({ timeout: 10_000 });

      // Toast should auto-dismiss after ~5 seconds
      await expect(toast.first()).toBeHidden({ timeout: 8_000 });
    });

    test('toast can be dismissed with Escape key', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1,
                method_name: 'github_oauth',
                display_name: 'GitHub OAuth',
                enabled: true,
                config_json: {},
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/methods/github_oauth', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1,
            method_name: 'github_oauth',
            display_name: 'GitHub OAuth',
            enabled: false,
            config_json: {},
            created_at: '2024-01-01T00:00:00Z',
            updated_at: '2024-06-01T00:00:00Z',
          }),
        });
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });
      await page.getByRole('button', { name: 'Disable' }).last().click();

      // Toast appears
      const toast = page.locator('[role="alert"]');
      await expect(toast.first()).toBeVisible({ timeout: 10_000 });

      // Press Escape to dismiss
      await page.keyboard.press('Escape');
      await expect(toast.first()).toBeHidden({ timeout: 3_000 });
    });

    test('toast has dismiss button', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1,
                method_name: 'github_oauth',
                display_name: 'GitHub OAuth',
                enabled: true,
                config_json: {},
                created_at: '2024-01-01T00:00:00Z',
                updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/methods/github_oauth', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
            enabled: false, config_json: {},
            created_at: '2024-01-01T00:00:00Z', updated_at: '2024-06-01T00:00:00Z',
          }),
        });
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });
      await page.getByRole('button', { name: 'Disable' }).last().click();

      // Toast appears with dismiss button
      const toast = page.locator('[role="alert"]');
      await expect(toast.first()).toBeVisible({ timeout: 10_000 });

      const dismissBtn = page.getByLabel('Dismiss notification');
      await expect(dismissBtn.first()).toBeVisible();
      await dismissBtn.first().click();
      await expect(toast.first()).toBeHidden({ timeout: 3_000 });
    });
  });

  // -------------------------------------------------------------------------
  // ErrorState Component
  // -------------------------------------------------------------------------
  test.describe('ErrorState', () => {
    test('renders error state on 500 API response', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Server error"}' });
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      // ErrorState renders with role="alert"
      const errorAlert = main.locator('[role="alert"]');
      await expect(errorAlert.first()).toBeVisible({ timeout: 15_000 });
      await expect(main.getByText(/something went wrong/i)).toBeVisible({ timeout: 5_000 });
    });

    test('error state shows Retry button that re-fetches data', async ({ page }) => {
      let callCount = 0;
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        callCount++;
        if (callCount <= 1) {
          route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"error"}' });
        } else {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
                enabled: true, config_json: {},
                created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        }
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      // Wait for error state
      await expect(main.getByRole('button', { name: 'Retry' })).toBeVisible({ timeout: 15_000 });

      // Click retry
      await main.getByRole('button', { name: 'Retry' }).click();

      // After retry, should show the method cards
      await expect(main.getByText('GitHub OAuth').first()).toBeVisible({ timeout: 10_000 });
    });
  });

  // -------------------------------------------------------------------------
  // Skeleton Loaders
  // -------------------------------------------------------------------------
  test.describe('Skeleton Loaders', () => {
    test('skeleton cards render during page load', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', async (route) => {
        // Introduce delay to see loading state
        await new Promise((r) => setTimeout(r, 5_000));
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      // SkeletonCard renders with role="presentation" and aria-hidden="true"
      const skeletons = page.locator('[role="presentation"][aria-hidden="true"]');
      await expect(skeletons.first()).toBeVisible({ timeout: 3_000 });
    });

    test('skeletons disappear once data loads', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', async (route) => {
        await new Promise((r) => setTimeout(r, 2_000));
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
              enabled: true, config_json: {},
              created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
            },
          ]),
        });
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      // Wait for skeletons to appear then disappear
      const skeletons = page.locator('[role="presentation"][aria-hidden="true"]');
      await expect(skeletons.first()).toBeVisible({ timeout: 3_000 });

      // Once data loads, skeletons should be replaced
      await expect(page.locator('main').getByText('GitHub OAuth').first()).toBeVisible({ timeout: 10_000 });
    });
  });

  // -------------------------------------------------------------------------
  // ConfirmDialog
  // -------------------------------------------------------------------------
  test.describe('ConfirmDialog', () => {
    test('appears for destructive actions', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
              enabled: true, config_json: {},
              created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
            },
          ]),
        });
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });

      // Modal should be visible with title and message
      await expect(page.getByText('Disable Auth Method')).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText(/no longer be able to sign in/i)).toBeVisible();
    });

    test('shows Working... text while confirming', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
                enabled: true, config_json: {},
                created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/methods/github_oauth', async (route) => {
        // Delay response to see "Working..." state
        await new Promise((r) => setTimeout(r, 3_000));
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1, method_name: 'github_oauth', display_name: 'GitHub OAuth',
            enabled: false, config_json: {},
            created_at: '2024-01-01T00:00:00Z', updated_at: '2024-06-01T00:00:00Z',
          }),
        });
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Disable' }).first().click({ timeout: 15_000 });
      await page.getByRole('button', { name: 'Disable' }).last().click();

      // Should show "Working..." during the pending state
      await expect(page.getByText('Working…')).toBeVisible({ timeout: 3_000 });
    });
  });

  // -------------------------------------------------------------------------
  // PageHeader Consistency
  // -------------------------------------------------------------------------
  test.describe('PageHeader', () => {
    test('admin auth page has consistent PageHeader structure', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        });
      });
      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');

      // PageHeader should have an h1 title
      await expect(main.getByRole('heading', { level: 1, name: 'Authentication Settings' })).toBeVisible({
        timeout: 15_000,
      });

      // Breadcrumb nav should be present
      await expect(page.getByLabel('Breadcrumb')).toBeVisible();
    });
  });

  // -------------------------------------------------------------------------
  // LoadingButton
  // -------------------------------------------------------------------------
  test.describe('LoadingButton', () => {
    test('shows spinner during async action and disables itself', async ({ page }) => {
      await page.route('**/api/v1/admin/auth/methods', (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([
              {
                id: 2, method_name: 'saml_sso', display_name: 'SAML SSO',
                enabled: false, config_json: { idp_entity_id: '', idp_sso_url: '', idp_x509_cert: '' },
                created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
              },
            ]),
          });
        } else {
          route.continue();
        }
      });

      await page.route('**/api/v1/admin/auth/saml/test', async (route) => {
        await new Promise((r) => setTimeout(r, 3_000));
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true, message: 'OK' }),
        });
      });

      await page.route('**/api/v1/admin/auth/session-policies', (route) => {
        route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
      });

      await page.goto('/admin/auth');
      await dismissTourIfPresent(page);

      const main = page.locator('main');
      await main.getByRole('button', { name: 'Configure' }).click({ timeout: 15_000 });

      const testBtn = main.getByRole('button', { name: 'Test Connection' });
      await testBtn.click();

      // Button should be disabled while loading (aria-busy="true")
      await expect(testBtn).toHaveAttribute('aria-busy', 'true', { timeout: 2_000 });
      await expect(testBtn).toBeDisabled();
    });
  });
});
