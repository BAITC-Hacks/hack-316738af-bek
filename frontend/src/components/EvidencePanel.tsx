import { useEffect, useState } from 'react';
import { Download, FileSearch, Quote } from 'lucide-react';
import type { AnalysisApi } from '../api/client';
import { saveBlob } from '../api/client';
import type { SourceEvidence, SourceSpan } from '../api/types';
import { locatorLabel, label } from '../lib/domain';
import { Alert, Badge, Dialog, Loading } from './common';

function QuoteBlock({ span }: { span: SourceSpan }) {
  return (
    <div className="quote-block">
      <div className="quote-locator">
        <Quote size={15} />
        {locatorLabel(span.locator)}
      </div>
      {span.section_path.length > 0 && (
        <p className="small muted">{span.section_path.join(' / ')}</p>
      )}
      <blockquote>{span.raw_text}</blockquote>
      <span className="source-id">Үзінді ID: {span.id}</span>
    </div>
  );
}
export function EvidencePanel({
  api,
  analysis,
  ids,
  title,
  demo,
  onClose,
}: {
  api: AnalysisApi;
  analysis: string;
  ids: string[];
  title: string;
  demo: boolean;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState(ids[0]);
  const [data, setData] = useState<SourceEvidence | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setData(null);
    setError('');
    api
      .source(analysis, selected, abort.signal)
      .then((next) => {
        if (abort.signal.aborted) return;
        if (next.source.id !== selected || next.source.document_id !== next.document.id)
          throw new Error('Дереккөздің идентификаторы сәйкес келмейді.');
        setData(next);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Дереккөз ашылмады.');
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [api, analysis, selected, retry]);
  const download = async () => {
    if (!data) return;
    setDownloading(true);
    setError('');
    try {
      saveBlob(await api.download(analysis, data.document.id), data.document.filename);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Файл жүктелмеді.');
    } finally {
      setDownloading(false);
    }
  };
  return (
    <Dialog title={title} onClose={onClose} wide>
      <div className="evidence-layout">
        <aside className="source-picker" aria-label="Дәлел үзінділері">
          {ids.map((id, i) => (
            <button
              key={id}
              className={selected === id ? 'selected' : ''}
              onClick={() => setSelected(id)}
              aria-pressed={selected === id}
            >
              <FileSearch size={17} />
              <span>
                Дәлел {i + 1}
                <small>{id}</small>
              </span>
            </button>
          ))}
        </aside>
        <div className="evidence-body">
          {loading ? (
            <Loading>Дереккөз ашылуда…</Loading>
          ) : (
            <>
              {error && (
                <Alert danger>
                  {error}
                  <button className="text-button" onClick={() => setRetry((t) => t + 1)}>
                    Қайта ашу
                  </button>
                </Alert>
              )}
              {data && (
                <>
                  <div className="source-document">
                    <span className="eyebrow">ТҮПНҰСҚА ҚҰЖАТ</span>
                    <h3>{data.document.title || data.document.filename}</h3>
                    <p>{data.document.filename}</p>
                    <div className="inline">
                      <Badge>{label(data.document.version)}</Badge>
                      {data.document.edition && (
                        <span className="small muted">{data.document.edition}</span>
                      )}
                    </div>
                  </div>
                  <QuoteBlock span={data.source} />
                  {data.context.length > 0 && (
                    <section className="context-section">
                      <h4>Басқарушы контекст</h4>
                      <p className="small muted">
                        Міндеттің кімге және қандай шартпен бекітілгенін түсіндіреді.
                      </p>
                      {data.context.map((s) => (
                        <QuoteBlock key={s.id} span={s} />
                      ))}
                    </section>
                  )}
                  <div className="source-footer">
                    <p>Үзінді бастапқы тілінде, өзгеріссіз көрсетілді.</p>
                    <button
                      className="button secondary"
                      disabled={demo || downloading}
                      onClick={() => void download()}
                    >
                      <Download size={16} />
                      {downloading ? 'Жүктелуде…' : 'Түпнұсқаны жүктеу'}
                    </button>
                    {demo && (
                      <p className="small muted">Жасанды мысалда түпнұсқа файл берілмеген.</p>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </Dialog>
  );
}
