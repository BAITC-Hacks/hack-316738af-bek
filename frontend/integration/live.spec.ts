import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'node:url';

test('real server: access → DOCX → AI → evidence → review → exports', async ({ page }) => {
  const judge = process.env.LIVE_FIXTURE_SET === 'judge';
  const fixtures = judge ? '../../backend/tests/fixtures/judge/' : '../../backend/tests/fixtures/';
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  if (await page.getByLabel('Қолжетімділік коды').isVisible()) {
    if (!process.env.APP_ACCESS_TOKEN)
      throw new Error('APP_ACCESS_TOKEN is required by this server');
    await page.getByLabel('Қолжетімділік коды').fill(process.env.APP_ACCESS_TOKEN);
    const login = page.waitForResponse(
      (r) => r.url().endsWith('/access') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Кіру', exact: true }).click();
    expect((await login).status()).toBe(303);
  }
  await expect(page.getByLabel('Дейін құжаттарын таңдау')).toBeAttached({ timeout: 10_000 });
  const created = page.waitForResponse(
    (r) => r.url().endsWith('/api/analyses') && r.request().method() === 'POST',
  );
  await page
    .getByLabel('Дейін құжаттарын таңдау')
    .setInputFiles(fileURLToPath(new URL(`${fixtures}before.docx`, import.meta.url)));
  const state = await (await created).json();
  await expect(page.getByRole('status')).toContainText('1 файл жүктелді');
  await page
    .getByLabel('Кейін құжаттарын таңдау')
    .setInputFiles(fileURLToPath(new URL(`${fixtures}after.docx`, import.meta.url)));
  await expect(page.getByRole('button', { name: 'Салыстыруды бастау' })).toBeEnabled();
  await page.getByRole('button', { name: 'Салыстыруды бастау' }).click();
  await expect(page.getByRole('heading', { name: 'Өзгерістер анық көрінеді.' })).toBeVisible({
    timeout: 200_000,
  });
  const response = await page.request.get(`/api/analyses/${state.analysis_id}/results`);
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  expect(
    result.usage.some(
      (u: { provider: string; calls: number }) => u.provider === 'openai' && u.calls > 0,
    ),
  ).toBeTruthy();
  expect(result.findings.length).toBeGreaterThan(0);
  if (judge) {
    expect(result.status).toBe('completed');
    expect(
      result.unit_changes.map((change: { change_type: string }) => change.change_type),
    ).toEqual(expect.arrayContaining(['renamed', 'preserved', 'created']));
    expect(result.findings.map((finding: { type: string }) => finding.type)).toEqual(
      expect.arrayContaining(['potential_loss', 'potential_duplicate']),
    );
  }
  await page
    .getByRole('button', { name: /Қолдайтын дәлел/ })
    .first()
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const original = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Түпнұсқаны жүктеу' }).click();
  expect((await original).suggestedFilename()).toMatch(/\.docx$/);
  await page.getByRole('button', { name: 'Жабу', exact: true }).click();
  await page.getByLabel('Тексеру күйі', { exact: true }).first().selectOption('confirmed');
  await page
    .getByLabel('Түсініктеме', { exact: true })
    .first()
    .fill('Live browser integration check');
  await page.getByRole('button', { name: 'Шешімді сақтау' }).first().click();
  await expect(page.getByText('Шешім мен түсініктеме сақталды.')).toBeVisible();
  await page.getByRole('button', { name: 'Есепке өту' }).click();
  for (const format of ['HTML', 'CSV']) {
    const report = page.waitForEvent('download');
    await page.getByRole('button', { name: `${format} жүктеу` }).click();
    expect((await report).suggestedFilename()).toMatch(new RegExp(`\\.${format.toLowerCase()}$`));
  }
  await page.reload();
  await expect(page.getByLabel('Тексеру күйі', { exact: true }).first()).toHaveValue('confirmed');
  expect(errors).toEqual([]);
});
