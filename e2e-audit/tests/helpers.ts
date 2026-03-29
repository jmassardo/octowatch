import { test as base, expect, Page } from '@playwright/test';

/**
 * Authenticate via dev-login and store cookies for reuse.
 * Also intercepts and logs every API response for analysis.
 */
export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // Dev-login
    const resp = await page.request.post('/api/v1/auth/dev-login', {
      data: { username: 'admin', password: 'admin' },
      ignoreHTTPSErrors: true,
    });
    expect(resp.ok()).toBeTruthy();

    // Collect API errors
    const apiErrors: { url: string; status: number; body: string }[] = [];
    page.on('response', async (response) => {
      const url = response.url();
      if (url.includes('/api/') && response.status() >= 400) {
        let body = '';
        try { body = await response.text(); } catch {}
        apiErrors.push({ url, status: response.status(), body: body.slice(0, 500) });
      }
    });

    // Collect console errors
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    // Attach collectors to page for later inspection
    (page as any).__apiErrors = apiErrors;
    (page as any).__consoleErrors = consoleErrors;

    await use(page);
  },
});

export { expect };

/** Navigate and wait for network idle */
export async function navigateTo(page: Page, path: string) {
  await page.goto(path, { waitUntil: 'networkidle', timeout: 15_000 });
}

/** Get API errors collected during the test */
export function getApiErrors(page: Page) {
  return (page as any).__apiErrors as { url: string; status: number; body: string }[];
}

/** Get console errors collected during the test */
export function getConsoleErrors(page: Page) {
  return (page as any).__consoleErrors as string[];
}
