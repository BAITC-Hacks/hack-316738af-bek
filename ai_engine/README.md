# AI қозғалтқышы

Qurylym AI құжат үзінділерінен функциялар мен жауаптыларды шығарып, нұсқаларды салыстырады және дереккөздері бар нәтижені қайтарады.

## Интерфейс

```python
from ai_engine.pipeline import analyze
result = await analyze(payload, emit_progress=save_progress)
```

Кіріс — `AnalysisInput`, нәтиже — `AnalysisResult`, API нұсқасы — 1.0.0. `save_progress` — async callback. `AnalysisError` қателігі `code`, `message`, `retryable` береді. Public функция ортаның айнымалыларын пайдаланады; файлды backend launcher немесе CLI оқиды.

## Құрылымы

| Файл | Міндеті |
|---|---|
| pipeline.py | Кезеңдер, timeout және қорытынды |
| extraction.py | Функциялар, субъектілер және мағыналық аудит |
| matching.py | Құрылым, функция сәйкестігі, жоғалуды қарсы тексеру |
| risks.py | Қайталану, қақтығыс, қарсы дәлел және тәуекел өзгерісі |
| providers.py | OpenAI/NVIDIA, retry, сұрау лимиті және usage |
| sources.py, validation.py | Түпнұсқа, дәйексөз, ID және санақ инварианттары |
| prompts.py | Нұсқаланған талдау нұсқаулары |

## Қайта тексеру

Репозиторий түбірінде:

```powershell
backend\.venv\Scripts\python -m evaluation.check
backend\.venv\Scripts\python -m ai_engine --env-file .env --config-check
backend\.venv\Scripts\python -m evaluation.run --live --all --env-file .env --output-dir evaluation/local_reports/live --max-total-calls 180
```

Бірінші команда тест provider қолданады; соңғысы нақты API кредитін жұмсайды. Кілттер серверде сақталады. Толық іске қосу, шектеулер және бағалау: [README](../README.md), [тексеру есебі](../docs/VERIFICATION.md).
