import type { AnalysisApi } from '../api/client';
import { ApiError } from '../api/client';
import { validate } from '../api/validation';
import type {
  AnalysisInput,
  AnalysisResult,
  AnalysisState,
  SourceEvidence,
  FindingReview,
} from '../api/types';
import stateData from './analysis_state.example.json';
import resultData from './analysis_result.example.json';
import inputData from './analysis_input.example.json';
import sourceData from './source_evidence.example.json';
import { safeRead, safeWrite } from '../lib/domain';

export function createDemoApi(): AnalysisApi {
  const state = validate<AnalysisState>('AnalysisState', structuredClone(stateData));
  const result = validate<AnalysisResult>('AnalysisResult', structuredClone(resultData));
  const input = validate<AnalysisInput>('AnalysisInput', inputData);
  const sampleSource = validate<SourceEvidence>('SourceEvidence', sourceData);
  const notes: Record<string, FindingReview> = {};
  for (const finding of result.findings) {
    try {
      const raw = safeRead(`qurylym:demo:review:${finding.id}`);
      if (raw) {
        const saved = validate<FindingReview>('FindingReview', JSON.parse(raw));
        notes[finding.id] = saved;
        finding.review_status = saved.review_status;
      }
    } catch {
      /* Ignore outdated demo-only data. */
    }
  }
  const unsupported = async (): Promise<never> => {
    throw new ApiError(
      400,
      'DEMO_ONLY',
      'Бұл жасанды мысалда файлдар өңделмейді. Нақты құжат үшін live режимін ашыңыз.',
    );
  };
  return {
    health: async () => ({
      status: 'ok',
      schema_version: '1.0.0',
      openai_configured: false,
      nvidia_configured: false,
    }),
    create: async () => structuredClone(state),
    state: async () => structuredClone(state),
    upload: unsupported,
    move: unsupported,
    run: async () => structuredClone(state),
    results: async () => structuredClone(result),
    source: async (_, id) => {
      if (id === sampleSource.source.id) return structuredClone(sampleSource);
      const doc = input.documents.find((d) => d.spans.some((s) => s.id === id));
      const source = doc?.spans.find((s) => s.id === id);
      if (!doc || !source) throw new ApiError(404, 'NOT_FOUND', 'Мысалда мұндай үзінді жоқ.');
      const { spans, ...document } = doc;
      return {
        document,
        source,
        context: spans.filter((s) => source.context_span_ids.includes(s.id)),
      };
    },
    review: async (_, id, patch) => {
      const f = result.findings.find((f) => f.id === id);
      if (!f) throw new ApiError(404, 'NOT_FOUND', 'Жағдай табылмады.');
      f.review_status = patch.review_status;
      const review = { finding_id: id, ...patch, reviewed_at: new Date().toISOString() };
      notes[id] = review;
      safeWrite(`qurylym:demo:review:${id}`, JSON.stringify(review));
      return review;
    },
    download: unsupported,
    export: async (_, format) => {
      const escape = (s: string) =>
        s.replace(
          /[&<>"']/g,
          (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
        );
      const csv = (s: string) => `"${(/^[=+\-@\t\r]/.test(s) ? "'" : '') + s.replace(/"/g, '""')}"`;
      const rows = result.findings.map((f) => [f.title, f.review_status, notes[f.id]?.note ?? '']);
      return format === 'csv'
        ? new Blob(
            [
              '\uFEFFЖасанды demo деректері\r\nТақырып,Шешім,Түсініктеме\r\n' +
                rows.map((r) => r.map(csv).join(',')).join('\r\n'),
            ],
            { type: 'text/csv;charset=utf-8' },
          )
        : new Blob(
            [
              `<!doctype html><html lang="kk"><meta charset="utf-8"><title>Qurylym AI — demo</title><h1>Жасанды demo деректері</h1><p>Нақты AI талдауы орындалмаған.</p>${rows.map((r) => `<section><h2>${escape(r[0])}</h2><p>${escape(r[1])}</p><p>${escape(r[2])}</p></section>`).join('')}</html>`,
            ],
            { type: 'text/html;charset=utf-8' },
          );
    },
  };
}
