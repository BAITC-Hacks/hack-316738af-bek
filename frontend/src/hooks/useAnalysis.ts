import { useCallback, useEffect, useRef, useState } from 'react';
import type { AnalysisApi } from '../api/client';
import { ApiError } from '../api/client';
import type { AnalysisResult, AnalysisState, FindingReview, ReviewPatch } from '../api/types';
import { isProcessing, isReady, safeRead, safeWrite } from '../lib/domain';

export function useAnalysis(api: AnalysisApi, demo: boolean) {
  const storageKey = `qurylym:${demo ? 'demo' : 'live'}:analysis`;
  const [id, setId] = useState<string | null>(() =>
    demo ? 'synthetic-demo' : safeRead(storageKey),
  );
  const [state, setState] = useState<AnalysisState | null>(null);
  const current = useRef<AnalysisState | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [reviews, setReviews] = useState<Record<string, FindingReview>>({});
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const epoch = useRef(0);
  const [restoring, setRestoring] = useState(!!id);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [retryTick, setRetryTick] = useState(0);
  const keys = useRef(new Map<string, string>());

  const accept = useCallback(
    (next: AnalysisState) => {
      if (
        current.current?.analysis_revision !== next.analysis_revision ||
        current.current?.analysis_id !== next.analysis_id ||
        !isReady(next.status)
      ) {
        setResult(null);
        setReviews({});
      }
      current.current = next;
      setState(next);
      setId(next.analysis_id);
      safeWrite(storageKey, next.analysis_id);
    },
    [storageKey],
  );
  const fetchResult = useCallback(
    async (next: AnalysisState, signal?: AbortSignal) => {
      if (!isReady(next.status)) return;
      const requestEpoch = epoch.current;
      const data = await api.results(next.analysis_id, signal);
      if (
        signal?.aborted ||
        requestEpoch !== epoch.current ||
        current.current?.analysis_id !== next.analysis_id ||
        current.current?.analysis_revision !== next.analysis_revision ||
        !isReady(current.current.status)
      )
        return;
      if (
        data.analysis_revision !== next.analysis_revision ||
        data.analysis_id !== next.analysis_id
      )
        throw new Error('Нәтиже нұсқасы өзгерді. Күйді жаңартып, қайта көріңіз.');
      setResult(data);
    },
    [api],
  );
  const refresh = useCallback(async () => {
    if (!id) return;
    const next = await api.state(id);
    accept(next);
    await fetchResult(next);
  }, [api, id, accept, fetchResult]);

  useEffect(() => {
    if (!id) {
      setRestoring(false);
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      if (lock.current) {
        timer = setTimeout(poll, 1000);
        return;
      }
      const requestEpoch = epoch.current;
      try {
        const next = await api.state(id, controller.signal);
        if (controller.signal.aborted) return;
        if (requestEpoch !== epoch.current || lock.current) {
          timer = setTimeout(poll, 1000);
          return;
        }
        accept(next);
        await fetchResult(next, controller.signal);
        if (controller.signal.aborted) return;
        if (requestEpoch !== epoch.current) {
          timer = setTimeout(poll, 1000);
          return;
        }
        failures = 0;
        setError('');
        setRestoring(false);
        if (isProcessing(next.status)) timer = setTimeout(poll, 1500);
      } catch (e) {
        if (controller.signal.aborted) return;
        if (requestEpoch !== epoch.current || lock.current) {
          timer = setTimeout(poll, 1000);
          return;
        }
        setError(e instanceof Error ? e.message : 'Күйді жүктеу мүмкін болмады.');
        setRestoring(false);
        if (e instanceof ApiError && e.status === 404) {
          safeWrite(storageKey, null);
          setId(null);
          current.current = null;
          setState(null);
          setResult(null);
        } else if (++failures <= 4 && (!(e instanceof ApiError) || e.retryable || e.status === 409))
          timer = setTimeout(poll, Math.min(2000 * failures, 8000));
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, api, accept, fetchResult, storageKey, retryTick]);

  const transact = useCallback(
    async <T>(action: () => Promise<T>): Promise<T | undefined> => {
      if (lock.current) return undefined;
      lock.current = true;
      epoch.current++;
      setBusy(true);
      setError('');
      setNotice('');
      try {
        return await action();
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          try {
            await refresh();
          } catch {
            /* Keep the original conflict message. */
          }
          setError(
            'Нұсқа өзгерген немесе сервер басқа талдауды орындап жатыр. Күй жаңартылды. ' +
              e.message,
          );
        } else setError(e instanceof Error ? e.message : 'Әрекет орындалмады.');
        return undefined;
      } finally {
        lock.current = false;
        setBusy(false);
      }
    },
    [refresh],
  );

  const upload = (files: File[], version: 'before' | 'after') =>
    transact(async () => {
      let next = current.current ?? (await api.create());
      accept(next);
      for (const file of files) {
        setNotice(`Жүктелуде: ${file.name}`);
        try {
          next = await api.upload(next.analysis_id, file, version);
          accept(next);
        } catch (e) {
          // Upload is non-idempotent: never retry automatically after an uncertain response.
          try {
            accept(await api.state(next.analysis_id));
          } catch {
            /* Explicit retry remains available. */
          }
          throw new Error(
            `${file.name}: ${e instanceof Error ? e.message : 'Жүктеу қатесі'}. Тізімді тексеріңіз; қалған файлдар жіберілген жоқ.`,
          );
        }
      }
      setNotice(`${files.length} файл жүктелді.`);
      setRetryTick((t) => t + 1);
    });
  const run = () =>
    transact(async () => {
      const active = current.current;
      if (!active) return;
      const keyName = `qurylym:run:${active.analysis_id}:${active.analysis_revision}`;
      const key = keys.current.get(keyName) ?? safeRead(keyName) ?? crypto.randomUUID();
      keys.current.set(keyName, key);
      safeWrite(keyName, key);
      const next = await api.run(active.analysis_id, active.analysis_revision, key);
      accept(next);
      await fetchResult(next);
      setRetryTick((t) => t + 1);
    });
  const move = (document: string, version: 'before' | 'after') =>
    transact(async () => {
      const active = current.current;
      if (!active) return;
      accept(
        await api.move(active.analysis_id, document, {
          version,
          expected_revision: active.analysis_revision,
        }),
      );
      setNotice('Құжаттың тобы өзгертілді. Жаңа салыстыруды бастаңыз.');
      setRetryTick((t) => t + 1);
    });
  const review = (finding: string, patch: ReviewPatch) =>
    transact(async () => {
      if (!id) return;
      const saved = await api.review(id, finding, patch);
      if (saved.finding_id !== finding || saved.analysis_revision !== patch.analysis_revision)
        throw new Error('Сақталған шешім нұсқасы сәйкес келмейді. Күйді жаңартыңыз.');
      setReviews((prev) => ({ ...prev, [finding]: saved }));
      setResult(
        (prev) =>
          prev && {
            ...prev,
            findings: prev.findings.map((f) =>
              f.id === finding ? { ...f, review_status: saved.review_status } : f,
            ),
          },
      );
      setNotice('Шешім сақталды.');
      return saved;
    });
  const reset = () => {
    if (lock.current) return;
    setId(null);
    current.current = null;
    setState(null);
    setResult(null);
    setReviews({});
    setError('');
    setNotice('');
    safeWrite(storageKey, null);
  };
  return {
    id,
    state,
    result,
    reviews,
    busy,
    restoring,
    error,
    notice,
    upload,
    run,
    move,
    review,
    reset,
    transact,
    setError,
    refresh: () => setRetryTick((t) => t + 1),
  };
}
