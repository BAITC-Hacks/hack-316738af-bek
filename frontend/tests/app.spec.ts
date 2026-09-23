import { test, expect, type Page, type Route } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import stateFixture from '../src/demo/analysis_state.example.json' with { type: 'json' };
import resultFixture from '../src/demo/analysis_result.example.json' with { type: 'json' };
import sourceFixture from '../src/demo/source_evidence.example.json' with { type: 'json' };
import inputFixture from '../src/demo/analysis_input.example.json' with { type: 'json' };
import type { AnalysisState, AnalysisResult, FindingReview } from '../src/api/types';

const state = () => structuredClone(stateFixture) as AnalysisState;
const result = () => structuredClone(resultFixture) as AnalysisResult;
const json = (route: Route, data: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
async function fixtureApi(
  page: Page,
  options: {
    fresh?: boolean;
    partial?: boolean;
    empty?: boolean;
    sourceFail?: boolean;
    reviewFail?: boolean;
    conflict?: boolean;
    networkRun?: boolean;
  } = {},
) {
  let current = state();
  let data = result();
  let polls = 0;
  let activeUploads = 0;
  let maxUploads = 0;
  const runKeys: string[] = [];
  const uploads: string[] = [];
  const reviews: FindingReview[] = [];
  if (options.fresh)
    current = {
      ...current,
      analysis_revision: 1,
      status: 'uploaded',
      documents: [],
      progress: { stage: 'uploaded', processed: 0, total: null, message: '' },
      warnings: [],
    };
  if (options.partial) {
    current.status = 'partial';
    data.status = 'partial';
    current.warnings = [
      { code: 'UNREADABLE', message: 'Скандағы мәтін оқылмады.', document_id: null, span_ids: [] },
    ];
    data.warnings = current.warnings;
  }
  if (options.empty) {
    data.findings = [];
    data.mappings = [];
    data.functions = [];
    data.units = [];
    data.unit_changes = [];
    data.coverage.before_functions_total = 0;
    data.coverage.full = 0;
    data.coverage.none = 0;
  }
  if (!options.fresh)
    await page.addInitScript(() =>
      sessionStorage.setItem('qurylym:live:analysis', 'synthetic-demo'),
    );
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    if (path === '/api/health')
      return json(route, {
        status: 'ok',
        schema_version: '1.0.0',
        openai_configured: true,
        nvidia_configured: false,
      });
    if (path === '/api/analyses' && req.method() === 'POST') return json(route, current, 201);
    if (path.endsWith('/documents') && req.method() === 'POST') {
      activeUploads++;
      maxUploads = Math.max(maxUploads, activeUploads);
      const body = req.postDataBuffer()?.toString('utf8') ?? '';
      const version = body.includes('\r\n\r\nafter\r\n') ? 'after' : 'before';
      uploads.push(version);
      await new Promise((resolve) => setTimeout(resolve, 70));
      const original = state().documents.find((d) => d.version === version)!;
      current.documents.push({
        ...original,
        version,
        id: current.documents.some((d) => d.id === original.id)
          ? `${original.id}-extra`
          : original.id,
      });
      current.analysis_revision++;
      current.status = 'uploaded';
      activeUploads--;
      return json(route, current, 201);
    }
    if (path.endsWith('/run')) {
      runKeys.push(req.headers()['idempotency-key']);
      expect(req.postDataJSON()).toEqual({ expected_revision: current.analysis_revision });
      if (options.networkRun && runKeys.length === 1) return route.abort('failed');
      current.status = 'matching';
      current.progress = {
        stage: 'matching',
        processed: 1,
        total: 2,
        message: 'Функциялар салыстырылуда',
      };
      polls = 0;
      return json(route, current, 202);
    }
    if (path.endsWith('/results')) {
      data.analysis_revision = current.analysis_revision;
      data.documents = current.documents;
      data.findings.forEach((f) => {
        f.analysis_revision = current.analysis_revision;
      });
      return json(route, data);
    }
    if (path.includes('/sources/')) {
      if (options.sourceFail)
        return json(
          route,
          { code: 'SOURCE_MISSING', message: 'Үзінді серверден табылмады.', retryable: false },
          404,
        );
      const id = decodeURIComponent(path.split('/').at(-1)!);
      const doc = inputFixture.documents.find((d) => d.spans.some((s) => s.id === id))!;
      const { spans, ...document } = doc;
      return json(route, { document, source: spans.find((s) => s.id === id), context: [] });
    }
    if (path.includes('/findings/') && req.method() === 'PATCH') {
      if (options.reviewFail)
        return json(
          route,
          { code: 'SAVE_ERROR', message: 'Шешім сақталмады.', retryable: true },
          500,
        );
      const saved = {
        ...req.postDataJSON(),
        finding_id: path.split('/').at(-1),
        reviewed_at: new Date().toISOString(),
      } as FindingReview;
      reviews.push(saved);
      data.findings.find((f) => f.id === saved.finding_id)!.review_status = saved.review_status;
      return json(route, saved);
    }
    if (path.endsWith('/download'))
      return route.fulfill({
        status: 200,
        contentType: 'application/octet-stream',
        body: 'test original bytes',
      });
    if (path.endsWith('/export')) {
      return route.fulfill({
        status: 200,
        contentType: url.searchParams.get('format') === 'html' ? 'text/html' : 'text/csv',
        body: `test export: ${reviews.map((r) => `${r.review_status},${r.note}`).join('\n')}`,
      });
    }
    if (path.includes('/documents/') && req.method() === 'PATCH') {
      const patch = req.postDataJSON();
      expect(patch.expected_revision).toBe(current.analysis_revision);
      if (options.conflict) {
        current.analysis_revision++;
        current.status = 'uploaded';
        return json(
          route,
          { code: 'REVISION_CONFLICT', message: 'Басқа терезеде нұсқа өзгерді.', retryable: false },
          409,
        );
      }
      current.documents.find((d) => d.id === path.split('/').at(-1))!.version = patch.version;
      current.analysis_revision++;
      current.status = 'uploaded';
      return json(route, current);
    }
    if (path === '/api/analyses/synthetic-demo') {
      if (current.status === 'matching' && ++polls >= 2) {
        current.status = 'completed';
        current.progress.stage = 'completed';
      }
      return json(route, current);
    }
    return json(route, { code: 'NOT_FOUND', message: 'Белгісіз маршрут', retryable: false }, 404);
  });
  return { runKeys, uploads, reviews, maxUploads: () => maxUploads };
}
async function navigate(page: Page, name: string) {
  const menu = page.getByRole('button', { name: 'Мәзірді ашу', exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole('navigation').getByRole('button', { name, exact: true }).click();
}

test('complete live-client workflow: sequential upload → run → evidence → review → exports → reload', async ({
  page,
}) => {
  const api = await fixtureApi(page, { fresh: true });
  const consoleErrors: string[] = [];
  page.on('pageerror', (e) => consoleErrors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Салыстыруды бастау' })).toBeDisabled();
  await page.getByLabel('Дейін құжаттарын таңдау').setInputFiles([
    { name: 'before.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('test docx') },
    {
      name: 'appendix.xlsx',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('test xlsx'),
    },
  ]);
  await expect(page.getByRole('status')).toContainText('2 файл жүктелді');
  await page.getByLabel('Кейін құжаттарын таңдау').setInputFiles({
    name: 'after.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('test pdf'),
  });
  await expect(page.getByRole('button', { name: 'Салыстыруды бастау' })).toBeEnabled();
  await page.getByRole('button', { name: 'Салыстыруды бастау' }).click();
  await expect(
    page.getByRole('heading', { name: 'Өзгерістерді байланыстырып жатырмыз' }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Өзгерістер анық көрінеді.' })).toBeVisible();
  expect(api.uploads).toEqual(['before', 'before', 'after']);
  expect(api.maxUploads()).toBe(1);
  expect(api.runKeys).toHaveLength(1);
  await page.getByRole('button', { name: /Қолдайтын дәлел/ }).click();
  await expect(
    page.getByRole('dialog').getByText(sourceFixture.source.raw_text, { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('dialog').getByText('2-тармақ', { exact: true })).toBeVisible();
  const originalDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Түпнұсқаны жүктеу' }).click();
  expect((await originalDownload).suggestedFilename()).toBe('demo-before.docx');
  await page.getByRole('button', { name: 'Жабу', exact: true }).click();
  await page.getByLabel('Тексеру күйі', { exact: true }).selectOption('confirmed');
  await page
    .getByLabel('Түсініктеме', { exact: true })
    .fill('Жауаптыны бөлім басшысымен нақтылау.');
  await page.getByRole('button', { name: 'Шешімді сақтау' }).click();
  await expect(page.getByText('Шешім мен түсініктеме сақталды.')).toBeVisible();
  expect(api.reviews[0]).toMatchObject({
    review_status: 'confirmed',
    note: 'Жауаптыны бөлім басшысымен нақтылау.',
    analysis_revision: 4,
  });
  await page.getByRole('button', { name: 'Есепке өту' }).click();
  for (const format of ['HTML', 'CSV']) {
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: `${format} жүктеу` }).click();
    expect((await download).suggestedFilename()).toMatch(new RegExp(`\\.${format.toLowerCase()}$`));
  }
  await page.reload();
  await expect(page.getByLabel('Тексеру күйі', { exact: true })).toHaveValue('confirmed');
  expect(consoleErrors).toEqual([]);
});

test('network run retry keeps the same idempotency key, including page refresh', async ({
  page,
}) => {
  const api = await fixtureApi(page, { fresh: true, networkRun: true });
  await page.goto('/');
  for (const v of ['Дейін', 'Кейін']) {
    await page.getByLabel(`${v} құжаттарын таңдау`).setInputFiles({
      name: `${v}.pdf`,
      mimeType: 'application/pdf',
      buffer: Buffer.from('test'),
    });
    await expect(page.getByRole('status')).toContainText('1 файл жүктелді');
  }
  await page.getByRole('button', { name: 'Салыстыруды бастау' }).click();
  await expect(page.getByRole('alert')).toContainText('Сервермен байланыс үзілді');
  await page.reload();
  await expect(page.getByRole('button', { name: 'Салыстыруды бастау' })).toBeEnabled();
  await page.getByRole('button', { name: 'Салыстыруды бастау' }).click();
  await expect(page.getByRole('heading', { name: 'Өзгерістер анық көрінеді.' })).toBeVisible();
  expect(api.runKeys).toHaveLength(2);
  expect(api.runKeys[0]).toBe(api.runKeys[1]);
});

test('loss has no invented after quote; filters, structure and original source work', async ({
  page,
}) => {
  await fixtureApi(page);
  await page.goto('/');
  await page.getByRole('tab', { name: /Функциялар/ }).click();
  await expect(page.getByText('Кейінгі жиында сәйкестік жоқ')).toBeVisible();
  await page.getByRole('button', { name: 'Негіздеме', exact: true }).last().click();
  await expect(page.getByText('Қамтылмаған:', { exact: false })).toBeVisible();
  await page.getByRole('tab', { name: /Құрылым/ }).click();
  await expect(page.getByRole('heading', { name: 'Құрылымдағы өзгерістер' })).toBeVisible();
  await page.getByRole('tab', { name: /Тәуекелдер/ }).click();
  await page.getByPlaceholder('Тәуекелді іздеу…').fill('no matching result');
  await expect(page.getByRole('heading', { name: 'Сүзгіге сай жағдай жоқ' })).toBeVisible();
  await page.getByRole('button', { name: 'Сүзгілерді тазалау' }).click();
  await expect(page.getByRole('button', { name: /ЖАҒДАЙ 01/ })).toBeVisible();
  await page.getByLabel('Түрі', { exact: true }).selectOption('potential_conflict');
  await expect(page.getByRole('heading', { name: 'Сүзгіге сай жағдай жоқ' })).toBeVisible();
});

test('409 refreshes state and removes stale results after moving a document', async ({ page }) => {
  await fixtureApi(page, { conflict: true });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Өзгерістер анық көрінеді.' })).toBeVisible();
  await navigate(page, 'Құжаттарды салыстыру');
  await page.getByRole('button', { name: 'demo-before.docx: Кейін тобына ауыстыру' }).click();
  await expect(page.getByRole('alert')).toContainText('Күй жаңартылды');
  const menu = page.getByRole('button', { name: 'Мәзірді ашу', exact: true });
  if (await menu.isVisible()) await menu.click();
  await expect(
    page.getByRole('navigation').getByRole('button', { name: 'Талдау нәтижелері' }),
  ).toBeDisabled();
});

test('partial result and diagnostics remain explicit', async ({ page }) => {
  await fixtureApi(page, { partial: true });
  await page.goto('/');
  await expect(page.getByText(/Нәтиже ішінара:/)).toBeVisible();
  await page.getByText('Диагностика және дерек шектеулері', { exact: false }).click();
  await expect(page.getByText('Скандағы мәтін оқылмады.')).toBeVisible();
});
test('empty result is usable and does not claim risk-free analysis', async ({ page }) => {
  await fixtureApi(page, { empty: true });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Тәуекелдер тізімі бос' })).toBeVisible();
  await page.getByRole('tab', { name: /Функциялар/ }).click();
  await expect(page.getByRole('heading', { name: 'Сәйкестік көрсетілмеген' })).toBeVisible();
});
test('server failure stays live and never silently becomes a demo', async ({ page }) => {
  await page.route('**/api/**', (route) =>
    json(
      route,
      { code: 'UNAVAILABLE', message: 'Сервер уақытша қолжетімсіз.', retryable: false },
      503,
    ),
  );
  await page.goto('/');
  await page
    .getByLabel('Дейін құжаттарын таңдау')
    .setInputFiles({ name: 'doc.pdf', mimeType: 'application/pdf', buffer: Buffer.from('test') });
  await expect(page.getByRole('alert')).toContainText('Сервер уақытша қолжетімсіз.');
  await expect(page.getByText('Жасанды demo деректері', { exact: true })).toHaveCount(0);
});
test('source and review failures cannot claim success', async ({ page }) => {
  await fixtureApi(page, { sourceFail: true, reviewFail: true });
  await page.goto('/');
  await page.getByRole('button', { name: /Қолдайтын дәлел/ }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText(
    'Үзінді серверден табылмады.',
  );
  await page.getByRole('button', { name: 'Жабу', exact: true }).click();
  await page.getByLabel('Тексеру күйі', { exact: true }).selectOption('confirmed');
  await page.getByRole('button', { name: 'Шешімді сақтау' }).click();
  await expect(page.getByRole('alert')).toContainText('Шешім сақталмады.');
  await expect(page.getByText('Шешім мен түсініктеме сақталды.')).toHaveCount(0);
});
test('invalid and too many files are rejected before API calls', async ({ page }) => {
  let requests = 0;
  await page.route('**/api/**', (route) => {
    if (!route.request().url().endsWith('/health')) requests++;
    return json(route, {
      status: 'ok',
      schema_version: '1.0.0',
      openai_configured: true,
      nvidia_configured: false,
    });
  });
  await page.goto('/');
  await page.getByLabel('Дейін құжаттарын таңдау').setInputFiles({
    name: 'unsupported.doc',
    mimeType: 'application/msword',
    buffer: Buffer.from('test'),
  });
  await expect(page.getByRole('alert')).toContainText('Тек DOCX, PDF немесе XLSX');
  await page.getByLabel('Дейін құжаттарын таңдау').setInputFiles(
    Array.from({ length: 11 }, (_, i) => ({
      name: `${i}.pdf`,
      mimeType: 'application/pdf',
      buffer: Buffer.from('test'),
    })),
  );
  await expect(page.getByRole('alert')).toContainText('ең көбі 10 файл');
  expect(requests).toBe(0);
});
test('explicit demo works offline, preserves label, saves review, exports safely', async ({
  page,
}) => {
  const apiRequests: string[] = [];
  await page.route('**/api/**', (route) => {
    apiRequests.push(route.request().url());
    return route.abort();
  });
  await page.goto('/?demo=1');
  await expect(page.getByText('Жасанды demo деректері', { exact: true })).toBeVisible();
  await page.getByLabel('Тексеру күйі', { exact: true }).selectOption('needs_information');
  await page.getByLabel('Түсініктеме', { exact: true }).fill('<script>alert(1)</script>');
  await page.getByRole('button', { name: 'Шешімді сақтау' }).click();
  await expect(page.getByText('Шешім мен түсініктеме сақталды.')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Тексеру күйі', { exact: true })).toHaveValue('needs_information');
  await page.getByRole('button', { name: 'Есепке өту' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'HTML жүктеу' }).click();
  const report = await download;
  expect(report.suggestedFilename()).toBe('qurylym-demo-v3.html');
  const html = await readFile((await report.path())!, 'utf8');
  expect(html).toContain('&lt;script&gt;');
  expect(html).not.toContain('<script>');
  expect(apiRequests).toEqual([]);
});

test('expired sessions and invalid API shapes show recovery, not a broken screen', async ({
  page,
}) => {
  await page.addInitScript(() => sessionStorage.setItem('qurylym:live:analysis', 'expired'));
  await page.route('**/api/**', (route) =>
    json(route, { code: 'NOT_FOUND', message: 'Сессия табылмады.', retryable: false }, 404),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Сессия табылмады.');
  await expect(page.getByRole('heading', { name: 'Салыстыруға арналған құжаттар' })).toBeVisible();
  await page.unroute('**/api/**');
  await page.route('**/api/**', (route) => json(route, { status: 'completed' }));
  await page
    .getByLabel('Дейін құжаттарын таңдау')
    .setInputFiles({ name: 'a.pdf', mimeType: 'application/pdf', buffer: Buffer.from('test') });
  await expect(page.getByRole('alert')).toContainText('API 1.0.0 келісіміне сәйкес емес');
});

test('untrusted original source is rendered as text and both evidence versions can be opened', async ({
  page,
}) => {
  await fixtureApi(page);
  const injection = '<img src=x onerror="window.pwned=true"> бастапқы мәтін';
  await page.route('**/sources/*', async (route) => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!;
    const evidence = structuredClone(sourceFixture);
    evidence.source.id = id;
    evidence.source.raw_text = injection;
    return json(route, evidence);
  });
  await page.goto('/');
  await page.getByRole('tab', { name: /Функциялар/ }).click();
  await page.getByRole('button', { name: 'Негіздеме', exact: true }).first().click();
  await page.getByRole('button', { name: /Сәйкестік дәлелдері/ }).click();
  await expect(page.getByRole('dialog').getByText(injection, { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog').locator('img')).toHaveCount(0);
  await page.getByRole('button', { name: /Дәлел 2/ }).click();
  await expect(page.getByText('Үзінді ID: a1')).toBeVisible();
  expect(await page.evaluate(() => 'pwned' in window)).toBe(false);
});

test('results from a different revision are rejected', async ({ page }) => {
  await fixtureApi(page);
  await page.route('**/results', (route) => json(route, { ...result(), analysis_revision: 999 }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Нәтиже нұсқасы өзгерді');
  await expect(page.getByRole('heading', { name: 'Өзгерістер анық көрінеді.' })).toHaveCount(0);
});

test('failed analysis diagnostics are shown and can be retried', async ({ page }) => {
  await fixtureApi(page);
  const failed = state();
  failed.status = 'failed';
  failed.progress.stage = 'failed';
  failed.warnings = [
    {
      code: 'PROVIDER_TIMEOUT',
      message: 'Модель уақытында жауап бермеді.',
      document_id: null,
      span_ids: [],
    },
  ];
  await page.route('**/api/analyses/synthetic-demo', (route) => json(route, failed));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Талдау аяқталмады');
  await expect(page.getByRole('button', { name: 'Салыстыруды бастау' })).toBeEnabled();
  await page.getByText('Диагностика және дерек шектеулері', { exact: false }).click();
  await expect(page.getByText('Модель уақытында жауап бермеді.')).toBeVisible();
});
test('upload and results are keyboard-accessible and have no horizontal page overflow', async ({
  page,
}) => {
  await fixtureApi(page, { fresh: true });
  await page.goto('/');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const uploadScan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    uploadScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/upload-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.goto('/?demo=1');
  await expect(page.getByRole('tab', { name: /Тәуекелдер/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('tab', { name: /Тәуекелдер/ }).focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: /Функциялар/ })).toBeFocused();
  await page.keyboard.press('Home');
  const resultScan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(
    resultScan.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
  ).toEqual([]);
  await page.screenshot({
    path: `test-results/results-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.getByRole('button', { name: /Қолдайтын дәлел/ }).click();
  await expect(page.getByRole('button', { name: 'Жабу', exact: true })).toBeFocused();
  const dialogScan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(dialogScan.violations.map((v) => v.id)).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Қолдайтын дәлел/ })).toBeFocused();
});
