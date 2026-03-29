import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'https://localhost',
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
  },
  reporter: [['list'], ['json', { outputFile: 'test-results.json' }]],
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
