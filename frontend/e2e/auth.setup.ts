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
import { test as setup } from '@playwright/test';
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

  // Navigate to a page first so cookies are set in the browser context.
  // Then call dev-login via fetch() inside the page context.
  await page.goto('/login');
  const status = await page.evaluate(
    async ({ username, password }) => {
      const res = await fetch('/api/v1/auth/dev-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      return res.status;
    },
    { username: user, password: pass },
  );

  if (status !== 200) {
    throw new Error(`dev-login failed with status ${status}`);
  }

  // Persist the authenticated browser state (cookies + localStorage) so that
  // downstream test projects can reuse it via the storageState option.
  await page.context().storageState({ path: AUTH_FILE });
});
