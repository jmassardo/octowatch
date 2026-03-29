import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 15_000 },
  workers: 1, // serialize to avoid rate limits on dev-login
  use: {
    baseURL: 'https://localhost',
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
  },
  reporter: [['list']],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
