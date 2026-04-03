/**
 * Playwright authentication setup — runs before smoke/navigation tests.
 *
 * Creates an authenticated session by calling the backend's dev-login
 * endpoint (available only when ENVIRONMENT != "production") and saves
 * the browser storage state for reuse by downstream test projects.
 *
 * Required env vars:
 *   E2E_USER — dev-login username (e.g. "admin")
 *   E2E_PASS — dev-login password (must equal username in dev mode)
 *
 * See frontend/.env.test.example for reference values.
 */
import { test as setup, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const AUTH_FILE = path.join(__dirname, '.auth', 'user.json');

setup('authenticate via dev-login', async ({ page }) => {
  const user = process.env.E2E_USER;
  const pass = process.env.E2E_PASS;

  if (!user || !pass) {
    throw new Error(
      'E2E_USER and E2E_PASS environment variables are required.\n' +
        'Create frontend/.env.test with:\n' +
        '  E2E_USER=admin\n' +
        '  E2E_PASS=admin\n' +
        'Then run: E2E_USER=admin E2E_PASS=admin npx playwright test\n' +
        'See frontend/.env.test.example for reference values.',
    );
  }

  // Ensure the .auth directory exists
  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });

  // POST to the dev-login endpoint (only available when ENVIRONMENT != production).
  // Using page.request so Set-Cookie headers are stored in the browser context.
  const response = await page.request.post('/api/v1/auth/dev-login', {
    data: { username: user, password: pass },
  });

  expect(response.ok()).toBeTruthy();

  // Persist the authenticated browser state (cookies + localStorage) so that
  // downstream test projects can reuse it via the storageState option.
  await page.context().storageState({ path: AUTH_FILE });
});
