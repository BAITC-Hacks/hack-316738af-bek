import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'live.spec.ts',
  timeout: 240_000,
  workers: 1,
  retries: 0,
  outputDir: '../test-results/live',
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.LIVE_BASE_URL || 'http://127.0.0.1:8766',
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: 'off',
  },
});
