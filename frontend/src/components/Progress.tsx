import { useEffect, useState } from 'react';
import { Check, LoaderCircle } from 'lucide-react';
import type { AnalysisState } from '../api/types';
import { label } from '../lib/domain';

export function Progress({ state }: { state: AnalysisState }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const stages = ['parsing', 'extracting', 'matching', 'verifying'];
  const position = stages.indexOf(state.status);
  const { processed, total, message } = state.progress;
  return (
    <section className="progress-card" aria-labelledby="progress-title">
      <div className="progress-symbol">
        <LoaderCircle className="spin" size={30} />
      </div>
      <span className="eyebrow">ТАЛДАУ ОРЫНДАЛЫП ЖАТЫР</span>
      <h1 id="progress-title">Өзгерістерді байланыстырып жатырмыз</h1>
      <p aria-live="polite">{message || label(state.status)}</p>
      <ol className="pipeline">
        {stages.map((s, i) => (
          <li key={s} className={i <= position ? 'active' : ''}>
            <span>{i < position ? <Check size={16} /> : i + 1}</span>
            {label(s)}
          </li>
        ))}
      </ol>
      <div className="stage-progress">
        <span>{label(state.progress.stage)}</span>
        <strong>
          {processed}
          {total == null ? ' өңделді' : ` / ${total}`}
        </strong>
      </div>
      {total != null && total > 0 && (
        <progress
          aria-label="Ағымдағы кезең прогресі"
          value={Math.min(processed, total)}
          max={total}
        />
      )}
      <p className="small muted">Бетті жаңартсаңыз да, талдау серверде жалғасады.</p>
      {seconds >= 45 && (
        <p className="long-running" role="status">
          Үлкен құжаттарды өңдеуге уақыт қажет. Соңғы кезең серверден жаңартылып жатыр.
        </p>
      )}
    </section>
  );
}
