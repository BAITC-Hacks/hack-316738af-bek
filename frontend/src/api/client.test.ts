import { describe, expect, it, vi } from 'vitest';
import { ApiError, createLiveApi } from './client';
import fixture from '../demo/analysis_state.example.json';

const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
describe('live API contract', () => {
  it('uses /api, credentials and URL-encoded IDs', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(fixture));
    await createLiveApi('', request).state('id/one?');
    expect(request.mock.calls[0][0]).toBe('/api/analyses/id%2Fone%3F');
    expect(request.mock.calls[0][1]?.credentials).toBe('include');
  });
  it.each(['https://example.test', 'https://example.test/', 'https://example.test/api/'])(
    'normalizes %s',
    async (base) => {
      const request = vi.fn<typeof fetch>().mockResolvedValue(response(fixture));
      await createLiveApi(base, request).state('x');
      expect(request.mock.calls[0][0]).toBe('https://example.test/api/analyses/x');
    },
  );
  it('preserves idempotency key and revision for retries', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('offline'))
      .mockResolvedValueOnce(response(fixture));
    const api = createLiveApi('', request);
    await expect(api.run('x', 3, 'same-key')).rejects.toBeInstanceOf(ApiError);
    await api.run('x', 3, 'same-key');
    for (const [, init] of request.mock.calls) {
      expect(init?.headers).toMatchObject({ 'Idempotency-Key': 'same-key' });
      expect(JSON.parse(init?.body as string)).toEqual({ expected_revision: 3 });
    }
  });
  it('propagates 409 rather than replacing it with mock data', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        response({ code: 'CONFLICT', message: 'revision changed', retryable: false }, 409),
      );
    await expect(createLiveApi('', request).run('x', 3, 'key')).rejects.toMatchObject({
      status: 409,
      code: 'CONFLICT',
    });
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('rejects malformed data and HTML proxy responses', async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(response({ status: 'completed' }))
      .mockResolvedValueOnce(new Response('<html>fallback</html>'));
    const api = createLiveApi('', request);
    await expect(api.state('x')).rejects.toThrow('келісіміне сәйкес емес');
    await expect(api.state('x')).rejects.toMatchObject({ code: 'INVALID_JSON' });
  });
  it('sends a single file and version with multipart boundaries managed by the browser', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(fixture));
    await createLiveApi('', request).upload('x', new File(['doc'], 'before.docx'), 'before');
    const init = request.mock.calls[0][1]!;
    expect(init.headers).toBeUndefined();
    expect((init.body as FormData).get('version')).toBe('before');
    expect((init.body as FormData).getAll('file')).toHaveLength(1);
  });
  it('does not retry a POST automatically', async () => {
    const request = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('network'));
    await expect(createLiveApi('', request).create()).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      retryable: true,
    });
    expect(request).toHaveBeenCalledTimes(1);
  });
  it.each([null, 'Bad gateway', 42])('handles unstructured error body %j', async (body) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(response(body, 502));
    await expect(createLiveApi('', request).state('x')).rejects.toMatchObject({
      status: 502,
      code: 'HTTP_ERROR',
    });
  });
});
