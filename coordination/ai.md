# AI қозғалтқышының тапсыру есебі

Тармақ: `team/ai-engine`. API: **1.0.0**, келісім файлы өзгертілмеді. Ортақ келісімнің бастапқы commit-і: `af7cc56` (алдыңғысы `0034f2e`). Код commit-і Git тарихындағы осы есеппен бірге беріледі.

## Дайын

- `ai_engine/pipeline.py`: `async def analyze(payload: dict, emit_progress=None) -> dict`.
- `ai_engine/errors.py`: `AnalysisError(code, message, retryable=False)`.
- Source registry, extraction + semantic audit, unit matching, exhaustive after partitions, raw-text loss countercheck, risks + counterevidence, validated result, usage/progress.
- OpenAI/NVIDIA HTTP клиенттері; default runtime-да тест нәтижесіне ауысу жоқ.
- CLI, pinned dependencies, 15 бақылау кірісі, бөлек labels, live evaluator.
- 32 автоматты тест өтті; `evaluation/engineering_checks.json` — нақты орындалу есебі.
- Ruff статикалық және формат тексерістері өтті; pip check үйлеспейтін тәуелділік таппады. PR-ға екі операциялық жүйеге арналған CI workflow қосылды.
- №8/№9 жергілікті 981 paragraph кіріс схемасына тексерілді; түпнұсқалар Git-ке кірмейді.
- `ba5c79d` commit-інің `core.autocrlf=false` таза жергілікті Git көшірмесінде 32 тест, Ruff check/format және келісім мысалының validation тексеруі қайта өтті. Бұл Windows-та LF checkout арқылы жасалған тексеру; Ubuntu орындалуы деп көрсетілмейді.

## GitHub CI нақты мәртебесі

[Run 35846867576](https://github.com/BAITC-Hacks/hack-316738af-bek/actions/runs/35846867576) екі job үшін де «The job was not started because your account is locked due to a billing issue.» хабарын көрсетті. Job қадамдары басталмаған, execution logs жасалмаған. GitHub-та Windows/Linux тесттері өтті деп есептелмейді. Аккаунт/ұйымның billing мәселесін тиісті әкімші шешкеннен кейін CI қайта жүргізіледі; жоба коды billing баптауын өзгертпейді.

## Backend иесіне

1. `python -m pip install -r ai_engine/requirements.txt` орнатыңыз, Python 3.11+ қолданыңыз.
2. Сервер процесіне `OPENAI_API_KEY`, `OPENAI_MODEL` беріңіз. Қалған env `ai_engine/.env.example` ішінде. Docker image-ге `contracts/openapi.json` да көшірілуі тиіс.
3. `AnalysisInput` схемасын дәл беріңіз: `span_count`, `parse_status`, бастапқы `raw_text`, context сілтемелері.
4. `await analyze(payload, emit_progress=async_callback)` шақырыңыз. Callback storage I/O қатесі талдауды бұзбай, диагностикаланады.
5. `AnalysisError.code/message/retryable` мәндерін келісімдегі error response-қа айналдырыңыз. Қате мәтініне кілт/толық құжат қоспаңыз.
6. `partial` нәтижені сақтап, frontend-ке жеткізіңіз. `unknown` ешқашан «жоғалған» деп көрсетілмейді.
7. Human review engine-де өзгермейді. Ревизия мен evidence қолжетімділігін backend тексереді.

## Frontend иесіне

- `source_span_ids`, `context_evidence_ids`, `counterevidence_ids` бойынша дәлел панелін көрсетіңіз.
- `verification_status=validated` маман бекіткен деген белгі емес; `review_status` бөлек.
- `search_complete=false`, `coverage.unknown`, document diagnostics көрінуі тиіс.
- UnitChange `basis=insufficient_data` кезінде created/removed мәндерін «жүктелген құжаттарда жаңадан көрсетілген/табылмаған» деп түсіндіріңіз.
- Көрінетін санақтарды backend result-тан алыңыз; жаңа denominator ойлап есептемеңіз.

## Орындалған тексеру

```text
python -m evaluation.check --report evaluation/engineering_checks.json
32 tests; 0 failures; 0 errors; 0 live API calls.
python -m evaluation.run --all --export-dir evaluation/fixtures
15 synthetic inputs exported; expected labels separate.
```

## Ашық қабылдау жұмысы

Нақты OpenAI және NVIDIA шақырулары credentials дайын болмағандықтан орындалған жоқ. Live модельдің дәлдігі, latency және credit шығыны өлшенбеген. Backend/frontend әлі бұл тармақта жоқ; толық Word/PDF/Excel → UI → evidence → review → export сценарийі біріктіргеннен кейін тексеріледі. Осы жағдайлар тексерілмей, толық өнім немесе 100 балл деп жариялауға болмайды.

## Қосу тәртібі

`main`-ға тікелей push автоматты рұқсат тексеруімен қабылданбады; ортақ келісім мен AI коды `team/ai-engine` тармағы және draft PR арқылы беріледі. Жаңа жұмыс көшірмесінде:

```text
git fetch origin
git switch -c team/backend af7cc56
```

Frontend иесі соңғы командада `team/frontend` қолданады. Өз тармағында жұмыс басталған болса, оны жоймай, екі келісім commit-ін біріктірушімен бірге қосады. Кейін тек өз каталогтарыңызға өзгеріс енгізіңіз. AI branch-ті біріктіру кезінде осы модульдің орнына екінші engine жазбаңыз. Келісімге өзгеріс керек болса, request файлы арқылы бір нұсқамен келісіңіз.
