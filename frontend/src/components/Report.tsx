import { Download, FileCheck2, FileSpreadsheet, ArrowRight } from 'lucide-react';
import type { AnalysisResult } from '../api/types';
import { Badge } from './common';

export function Report({
  result,
  busy,
  demo,
  download,
  onReference,
}: {
  result: AnalysisResult;
  busy: boolean;
  demo: boolean;
  download: (format: 'html' | 'csv') => void;
  onReference: (id: string) => void;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ҚОРЫТЫНДЫ ЖӘНЕ ЭКСПОРТ</span>
          <h1>Шешім қабылдауға дайын.</h1>
          <p>AI қорытындысы, дереккөздер және қызметкер шешімдері бір есепте.</p>
        </div>
        <Badge value={result.status} />
      </div>
      <div className="report-layout">
        <section className="report-preview">
          <div className="report-paper-head">
            <span className="brand-small">
              Q<span>urylym</span> AI
            </span>
            <span>ТАЛДАУ ЕСЕБІ · {result.analysis_revision}</span>
          </div>
          {demo && <p className="demo-watermark">Жасанды demo деректері</p>}
          <h2>{result.summary.headline}</h2>
          <p className="muted">
            {result.documents.length} құжат · {result.coverage.before_functions_total} бұрынғы
            функция
          </p>
          <ol className="summary-items">
            {result.summary.items.map((item, i) => (
              <li key={i}>
                <span>{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <p>{item.text}</p>
                  <div className="inline">
                    {item.reference_ids.map((id) => (
                      <button key={id} className="text-button" onClick={() => onReference(id)}>
                        Негіздеме · {id}
                        <ArrowRight size={14} />
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          <h3>Деректердің шектеулері</h3>
          <p>
            Қорытынды тек жүктелген жиынға қатысты. AI ұсынған жағдайларды қызметкер дереккөздер
            арқылы бағалайды.
          </p>
          {result.warnings.map((w, i) => (
            <p className="report-warning" key={`${w.code}-${i}`}>
              {w.message}
            </p>
          ))}
          <div className="report-signoff">
            <FileCheck2 size={18} />
            <span>
              {result.coverage.evidence_links_valid} / {result.coverage.evidence_links_total}{' '}
              сілтеме тексерілген
            </span>
          </div>
        </section>
        <aside className="export-options">
          <h2>Есепті жүктеу</h2>
          <p>Өзіңізге ыңғайлы пішімді таңдаңыз.</p>
          <article>
            <FileCheck2 size={24} />
            <h3>Толық есеп</h3>
            <p>Қорытынды, дәлелдер және сақталған шешімдер. Браузерде ашуға болады.</p>
            <button className="button primary" disabled={busy} onClick={() => download('html')}>
              <Download size={16} />
              HTML жүктеу
            </button>
          </article>
          <article>
            <FileSpreadsheet size={24} />
            <h3>Жұмыс кестесі</h3>
            <p>Әрі қарай сүзу және өңдеу үшін Excel-ге ашылатын CSV кестесі.</p>
            <button className="button secondary" disabled={busy} onClick={() => download('csv')}>
              <Download size={16} />
              CSV жүктеу
            </button>
          </article>
          {demo && <p className="small muted">Демо экспорты жасанды мысал ретінде белгіленеді.</p>}
        </aside>
      </div>
    </>
  );
}
