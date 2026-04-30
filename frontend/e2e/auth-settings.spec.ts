import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Authentication Settings E2E Tests
//
// Tests the /admin/auth page which manages SSO/SAML settings, auth method
// toggling, and session policies.
// ---------------------------------------------------------------------------

const AUTH_METHODS_MOCK = [
  {
    id: 1,
    method_name: 'github_oauth',
    display_name: 'GitHub OAuth',
    enabled: true,
    config_json: { client_id: 'abc123' },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    method_name: 'saml_sso',
    display_name: 'SAML SSO',
    enabled: false,
    config_json: { idp_entity_id: '', idp_sso_url: '', idp_x509_cert: '' },
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 3,
    method_name: 'local_password',
    display_name: 'Dev Login',
    enabled: true,
    config_json: {},
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

const SESSION_POLICIES_MOCK = [
  {
    id: 1,
    policy_key: 'session_timeout_minutes',
    policy_value: '480',
    description: 'Maximum session duration in minutes',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 2,
    policy_key: 'idle_timeout_minutes',
    policy_value: '60',
    description: 'Idle timeout before session expires',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 3,
    policy_key: 'max_concurrent_sessions',
    policy_value: '5',
    description: 'Maximum concurrent sessions per user',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

/** Dismiss the guided tour if it appears. */
async function dismissTourIfPresent(page: Page) {
  const closeBtn = page.getByRole('button', { name: 'Close tour' });
  if (await closeBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await closeBtn.click();
    await expect(page.getByRole('dialog', { name: 'Guided tour' })).toBeHidden({ timeout: 3_000 });
  }
}

/** Set up API route mocks for the auth settings page. */
async function setupAuthMocks(page: Page) {
  await page.route('**/api/v1/admin/auth/methods', (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUTH_METHODS_MOCK),
      });
    } else {
      route.continue();
    }
  });

  await page.route('**/api/v1/admin/auth/session-policies', (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SESSION_POLICIES_MOCK),
      });
    } else {
      route.continue();
    }
  });
}

test.describe('Authentication Settings Page', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  test('renders page header with title and description', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await expect(main.getByText('Authentication Settings').first()).toBeVisible({ timeout: 15_000 });
    await expect(main.getByText('Manage sign-in methods').first()).toBeVisible({ timeout: 10_000 });
  });

  test('renders breadcrumbs with Admin > Authentication', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const breadcrumb = page.getByLabel('Breadcrumb');
    await expect(breadcrumb).toBeVisible({ timeout: 10_000 });
    await expect(breadcrumb.getByText('Admin')).toBeVisible();
    await expect(breadcrumb.getByText('Authentication')).toBeVisible();
  });

  test('displays all three auth methods (GitHub OAuth, SAML SSO, Dev Login)', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await expect(main.getByText('GitHub OAuth').first()).toBeVisible({ timeout: 15_000 });
    await expect(main.getByText('SAML SSO').first()).toBeVisible({ timeout: 10_000 });
    await expect(main.getByText('Dev Login').first()).toBeVisible({ timeout: 10_000 });
  });

  test('shows Enabled/Disabled badges for auth methods', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    // GitHub OAuth and Dev Login are enabled; SAML is disabled
    const enabledBadges = main.getByText('Enabled');
    const disabledBadges = main.getByText('Disabled');

    await expect(enabledBadges.first()).toBeVisible({ timeout: 15_000 });
    await expect(disabledBadges.first()).toBeVisible({ timeout: 10_000 });
  });

  test('toggle button shows "Disable" for enabled and "Enable" for disabled methods', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    // Should have both "Enable" and "Disable" buttons depending on state
    await expect(main.getByRole('button', { name: 'Disable' }).first()).toBeVisible({ timeout: 15_000 });
    await expect(main.getByRole('button', { name: 'Enable' }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking Disable shows confirmation dialog', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    // Click the first Disable button (GitHub OAuth)
    await main.getByRole('button', { name: 'Disable' }).first().click();

    // Confirm dialog should appear
    await expect(page.getByText('Disable Auth Method')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/Are you sure you want to disable/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Disable' }).last()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  });

  test('cancel in confirmation dialog closes it without action', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await main.getByRole('button', { name: 'Disable' }).first().click();

    // Click Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Dialog should close
    await expect(page.getByText('Disable Auth Method')).toBeHidden({ timeout: 3_000 });
  });

  test('SAML SSO has a Configure button', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await expect(main.getByRole('button', { name: 'Configure' })).toBeVisible({ timeout: 15_000 });
  });

  test('clicking Configure shows SAML configuration form', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await main.getByRole('button', { name: 'Configure' }).click();

    // SAML config section should appear
    await expect(main.getByText('SAML Configuration')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('#idp-entity-id')).toBeVisible();
    await expect(page.locator('#idp-sso-url')).toBeVisible();
    await expect(page.locator('#idp-cert')).toBeVisible();
  });

  test('SAML form has Test Connection and Save Configuration buttons', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await main.getByRole('button', { name: 'Configure' }).click();

    await expect(main.getByRole('button', { name: 'Test Connection' })).toBeVisible({ timeout: 5_000 });
    await expect(main.getByRole('button', { name: 'Save Configuration' })).toBeVisible();
  });

  test('SAML form can be filled with IdP metadata', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await main.getByRole('button', { name: 'Configure' }).click();

    // Fill in SAML fields
    await page.locator('#idp-entity-id').fill('https://idp.example.com/entity');
    await page.locator('#idp-sso-url').fill('https://idp.example.com/sso');
    await page.locator('#idp-cert').fill('-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----');

    // Verify values are set
    await expect(page.locator('#idp-entity-id')).toHaveValue('https://idp.example.com/entity');
    await expect(page.locator('#idp-sso-url')).toHaveValue('https://idp.example.com/sso');
    await expect(page.locator('#idp-cert')).toHaveValue(/BEGIN CERTIFICATE/);
  });

  test('Test Connection button calls SAML test endpoint', async ({ page }) => {
    await setupAuthMocks(page);

    let testCalled = false;
    await page.route('**/api/v1/admin/auth/saml/test', (route) => {
      testCalled = true;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'SAML IdP metadata endpoint is reachable.',
          details: { idp_status: 'ok' },
        }),
      });
    });

    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await main.getByRole('button', { name: 'Configure' }).click();
    await main.getByRole('button', { name: 'Test Connection' }).click();

    // Wait for toast or some indication of success
    await page.waitForTimeout(1_000);
    expect(testCalled).toBe(true);
  });

  test('Session Policies section renders policy table', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await expect(main.getByText('Session Policies').first()).toBeVisible({ timeout: 15_000 });
    await expect(main.getByText('session_timeout_minutes')).toBeVisible({ timeout: 10_000 });
    await expect(main.getByText('idle_timeout_minutes')).toBeVisible({ timeout: 10_000 });
    await expect(main.getByText('max_concurrent_sessions')).toBeVisible({ timeout: 10_000 });
  });

  test('Session policy values are editable', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    // Wait for session policies to render
    await expect(main.getByText('session_timeout_minutes')).toBeVisible({ timeout: 15_000 });

    // Find the input for session_timeout_minutes and change it
    const policyInputs = main.locator('input[class*="policyInput"]');
    const firstInput = policyInputs.first();
    await expect(firstInput).toBeVisible({ timeout: 5_000 });

    await firstInput.clear();
    await firstInput.fill('720');
    await expect(firstInput).toHaveValue('720');
  });

  test('Save button is disabled when value unchanged', async ({ page }) => {
    await setupAuthMocks(page);
    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    await expect(main.getByText('session_timeout_minutes')).toBeVisible({ timeout: 15_000 });

    // Save buttons should be disabled when values match initial state
    const saveButtons = main.getByRole('button', { name: 'Save' });
    const firstSave = saveButtons.first();
    await expect(firstSave).toBeVisible({ timeout: 5_000 });
    await expect(firstSave).toBeDisabled();
  });

  test('error state renders on API failure with retry button', async ({ page }) => {
    // Mock methods endpoint to fail
    await page.route('**/api/v1/admin/auth/methods', (route) => {
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal error"}' });
    });
    await page.route('**/api/v1/admin/auth/session-policies', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SESSION_POLICIES_MOCK),
      });
    });

    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    const main = page.locator('main');
    // ErrorState should render with a Retry button
    await expect(main.getByText(/something went wrong/i).or(main.getByRole('button', { name: 'Retry' }))).toBeVisible({
      timeout: 15_000,
    });
  });

  test('loading state shows skeleton cards', async ({ page }) => {
    // Mock methods endpoint with a delay to catch skeleton state
    await page.route('**/api/v1/admin/auth/methods', async (route) => {
      await new Promise((r) => setTimeout(r, 3_000));
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUTH_METHODS_MOCK),
      });
    });
    await page.route('**/api/v1/admin/auth/session-policies', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SESSION_POLICIES_MOCK),
      });
    });

    await page.goto('/admin/auth');
    await dismissTourIfPresent(page);

    // While loading, skeleton cards should be visible (they have role="presentation")
    const skeletons = page.locator('[role="presentation"]');
    await expect(skeletons.first()).toBeVisible({ timeout: 5_000 });
  });
});
