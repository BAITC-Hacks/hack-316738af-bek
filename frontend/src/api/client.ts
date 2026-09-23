import type {
  AnalysisState,
  AnalysisResult,
  DocumentPatch,
  SourceEvidence,
  ReviewPatch,
  FindingReview,
  Health,
} from './types';
import { validate } from './validation';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable = false,
  ) {
    super(message);
  }
}
export interface AnalysisApi {
  health(signal?: AbortSignal): Promise<Health>;
  create(): Promise<AnalysisState>;
  state(id: string, signal?: AbortSignal): Promise<AnalysisState>;
  upload(id: string, file: File, version: 'before' | 'after'): Promise<AnalysisState>;
  move(id: string, document: string, patch: DocumentPatch): Promise<AnalysisState>;
  run(id: string, revision: number, key: string): Promise<AnalysisState>;
  results(id: string, signal?: AbortSignal): Promise<AnalysisResult>;
  source(id: string, source: string, signal?: AbortSignal): Promise<SourceEvidence>;
  review(id: string, finding: string, patch: ReviewPatch): Promise<FindingReview>;
  download(id: string, document: string): Promise<Blob>;
  export(id: string, format: 'html' | 'csv'): Promise<Blob>;
}
const part = encodeURIComponent;
export function createLiveApi(
  base = import.meta.env.VITE_API_BASE_URL ?? '',
  fetcher: typeof fetch = fetch,
): AnalysisApi {
  const origin = base.trim().replace(/\/+$/, '');
  // Accept an origin or an explicit /api base, without ever duplicating /api.
  const prefix = origin.endsWith('/api') ? origin : `${origin}/api`;
  async function request(path: string, init: RequestInit = {}, schema?: string): Promise<unknown> {
    const timeout = AbortSignal.timeout(60_000);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    let response: Response;
    try {
      response = await fetcher(`${prefix}${path}`, { ...init, credentials: 'include', signal });
    } catch (e) {
      if (init.signal?.aborted) throw e;
      throw new ApiError(
        0,
        'NETWORK_ERROR',
        'Сервермен байланыс үзілді немесе сұрау уақыты аяқталды. Қайта байқап көріңіз.',
        true,
      );
    }
    if (!response.ok) {
      let data: { code?: unknown; message?: unknown; retryable?: unknown } = {};
      try {
        const body: unknown = await response.json();
        if (body && typeof body === 'object') data = body;
      } catch {
        /* Proxy may return plain text. */
      }
      throw new ApiError(
        response.status,
        typeof data.code === 'string' ? data.code : 'HTTP_ERROR',
        typeof data.message === 'string'
          ? data.message
          : `Сұрау орындалмады (${response.status}). Сервер қолжетімділігін тексеріңіз.`,
        data.retryable === true,
      );
    }
    if (!schema) return response.blob();
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new ApiError(
        response.status,
        'INVALID_JSON',
        'Сервер JSON орнына басқа жауап берді. API мекенжайын тексеріңіз.',
      );
    }
    return validate(schema, data);
  }
  const json = (
    method: string,
    data: unknown,
    extra: Record<string, string> = {},
  ): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json', ...extra },
    body: JSON.stringify(data),
  });
  const path = (id: string) => `/analyses/${part(id)}`;
  return {
    health: (signal) => request('/health', { signal }, 'Health') as Promise<Health>,
    create: () =>
      request('/analyses', { method: 'POST' }, 'AnalysisState') as Promise<AnalysisState>,
    state: (id, signal) => request(path(id), { signal }, 'AnalysisState') as Promise<AnalysisState>,
    upload: (id, file, version) => {
      const body = new FormData();
      body.append('version', version);
      body.append('file', file);
      return request(
        `${path(id)}/documents`,
        { method: 'POST', body },
        'AnalysisState',
      ) as Promise<AnalysisState>;
    },
    move: (id, document, patch) =>
      request(
        `${path(id)}/documents/${part(document)}`,
        json('PATCH', patch),
        'AnalysisState',
      ) as Promise<AnalysisState>,
    // The caller persists this key per analysis + revision, including uncertain network outcomes.
    run: (id, revision, key) =>
      request(
        `${path(id)}/run`,
        json('POST', { expected_revision: revision }, { 'Idempotency-Key': key }),
        'AnalysisState',
      ) as Promise<AnalysisState>,
    results: (id, signal) =>
      request(`${path(id)}/results`, { signal }, 'AnalysisResult') as Promise<AnalysisResult>,
    source: (id, source, signal) =>
      request(
        `${path(id)}/sources/${part(source)}`,
        { signal },
        'SourceEvidence',
      ) as Promise<SourceEvidence>,
    review: (id, finding, patch) =>
      request(
        `${path(id)}/findings/${part(finding)}`,
        json('PATCH', patch),
        'FindingReview',
      ) as Promise<FindingReview>,
    download: (id, document) =>
      request(`${path(id)}/documents/${part(document)}/download`) as Promise<Blob>,
    export: (id, format) => request(`${path(id)}/export?format=${format}`) as Promise<Blob>,
  };
}
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
