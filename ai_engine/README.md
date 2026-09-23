# Qurylym AI — AI қозғалтқышы

Ұйымдық құжаттардың «дейінгі» және «кейінгі» нұсқаларын салыстыратын Python модулі. Пайдаланушы — бөлімшелерді қайта ұйымдастыруды тексеретін қызметкер. Модуль функцияларды, жауаптыларды және ықтимал ауытқуларды бастапқы үзінділерге байланыстырады.

**Мәртебе:** код пен API-сыз инженерлік тесттер дайын. Нақты OpenAI/NVIDIA сапасы бұл commit-те өлшенген жоқ. Бұл модуль команданың backend және frontend бөліктеріне қосылады.

## 1. Іске асырылған мүмкіндіктер

- Құжат үзінділерінен бөлімше, лауазым, функция, міндет, рұқсат, тыйым, шарт және мерзімді шығару.
- Дәйексөздің бастапқы мәтінде бар екенін тексеру; кейін бөлек AI сұрауымен мағыналық негізділігін тексеру.
- Бөлімшелердің сақталуын, кейінгі құрылымда жаңадан көрсетілуін, атауы өзгеруін, бірігуін, бөлінуін және бағыныштылық өзгерісін көрсету.
- Формалды қайта ұйымдастыруды тек берілген өкім/құжат растаса белгілеу. Құжатта атаудың болмауы заңды таратылудың дәлелі деп көрсетілмейді.
- Бұрынғы функцияларды барлық кейінгі бөлімшелерден іздеу: `full`, `partial`, `none`, `unknown`.
- Функцияның ауысуы, мерзім/ауқым/өкілеттік өзгерісі, бөлінуі және бірігуі.
- Жоғалу гипотезасын кейінгі құжаттардың **бастапқы мәтінімен қайта тексеру**. Мәтіннен ықтимал сәйкестік табылса, нәтиже `unknown` болады.
- Екі нұсқадағы ықтимал қайталану және үйлеспейтін рөлдер; бұрыннан бар тәуекелді жаңа тәуекелден ажырату.
- Қақтығыс үшін екі функцияның дәлелімен бірге берілген тәуелсіздік/тыйым талабын сұрау; қорғаныс шараларын бөлек тексеру.
- Белгісіз жауапты, бос нөмірленген тармақ және толық оқылмаған құжат диагностикасы.
- JSON Schema, нұсқа, ID, иерархия, санақ және evidence сілтемелерін кодпен тексеру.
- Нақты API usage, сұрау лимиті, timeout, retry, прогресс және бір талдау ішіндегі кэш.

`validated` — техникалық және белгіленген AI тексерулері өткен белгі. Қызметкердің шешімі әрдайым `unreviewed` күйінде беріледі.

## 2. Негізгі сценарий

Backend Word/PDF/Excel файлдарын оқып, `AnalysisInput` жасайды. Қозғалтқыш кірісті тексереді, функцияларды шығарады, дәлелдерді тексереді, нұсқаларды салыстырады, тәуекелдерді қайта қарайды және `AnalysisResult` қайтарады. Frontend осы нәтижеден салыстыру кестесін және evidence панелін көрсетеді.

Файл жүктеу, DOCX/PDF/XLSX парсингі, дерекқор, HTTP маршруттар, review сақтау және экспорт — backend бөлігі. Браузер интерфейсі — frontend бөлігі.

## 3. Технологиялар мен архитектура

Python **3.11+** қажет; жергілікті тексерілген нұсқа — **3.12.14**. Runtime тәуелділіктері `requirements.txt` ішінде толық бекітілген. HTTP үшін Python `urllib`, concurrency үшін `asyncio`, схема үшін `jsonschema` қолданылады.

| Компонент | Міндеті |
|---|---|
| `pipeline.py` | Оркестрация, прогресс, жалпы timeout, нәтиже құрастыру |
| `sources.py` | Өзгертілмейтін дереккөз тізілімі, context, quote, көлем шектері |
| `extraction.py` | Үзінділерді бөліп өңдеу, entity/function шығару және аудит |
| `matching.py` | Функция сәйкестігі, толық іздеу, жоғалуды қарсы тексеру, құрылым |
| `risks.py` | Қайталану/қақтығыс кандидаттары, дәлел, қарсы дәлел, тәуекел өзгерісі |
| `providers.py` | OpenAI Responses және NVIDIA embeddings клиенттері |
| `schema.py`, `validation.py` | Ортақ келісім және объектілер арасындағы инварианттар |
| `prompts.py` | Нұсқаланған нұсқаулар: `qurylym-1.0.0` |
| `evaluation/` | Бақылау кірістері, бөлек күтілетін белгілер және нақты модельді бағалау |

Қысқаша қорытынды тек тексерілген жазбалардан шаблон арқылы жиналады. Санақтар LLM-ге есептетілмейді. Барлық модель сұрауы нақты берілген деректермен шектеледі; құжаттағы командалар нұсқаулық ретінде қабылданбауы тиіс.

## 4. Орнату

Барлық команданы **репозиторий түбірінде** орындаңыз.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ai_engine/requirements.txt
Copy-Item ai_engine/.env.example ai_engine/.env
```

Linux/macOS-та interpreter жолы: `.venv/bin/python`.

`ai_engine/.env` файлына кілтті жергілікті редактор арқылы енгізіңіз. Бұл файл engine `.gitignore` тізімінде. Серверде сол мәндерді орта айнымалылары ретінде орнатуға болады. Backend өз `.env` файлын өзі жүктейді; public Python `analyze` функциясы файл іздемейді.

```dotenv
OPENAI_API_KEY=жергілікті_кілт
OPENAI_MODEL=gpt-4.1
NVIDIA_ENABLED=false
NVIDIA_API_KEY=
NVIDIA_EMBED_MODEL=nvidia/llama-nemotron-embed-1b-v2
ANALYSIS_TIMEOUT_SECONDS=600
AI_REQUEST_TIMEOUT_SECONDS=90
AI_MAX_REQUESTS=100
AI_MAX_OUTPUT_TOKENS=12000
AI_CONCURRENCY=3
```

`gpt-4.1` — конфигурация мысалы; осы жобадағы сапасы әлі өлшенбеген. Ол Responses және Structured Outputs қолдайды. Өз аккаунтыңызда қолжетімді басқа үйлесімді модельді `OPENAI_MODEL` арқылы таңдауға болады. [OpenAI модель құжаты](https://developers.openai.com/api/docs/models/gpt-4.1).

Дайындықты кілтті экранға шығармай тексеру:

```powershell
.\.venv\Scripts\python.exe -m ai_engine --env-file ai_engine/.env --config-check
```

## 5. Backend-ке қосу — өзгермейтін интерфейс

```python
from ai_engine.pipeline import analyze
from ai_engine.errors import AnalysisError

async def run_analysis(parsed_input, save_progress):
    try:
        result = await analyze(parsed_input, emit_progress=save_progress)
        return result
    except AnalysisError as exc:
        # Backend келісімдегі ErrorResponse түріне айналдырады.
        raise RuntimeError(exc.code) from None

async def save_progress(event):
    # event: stage, processed, total, message
    await storage.save_progress(event)  # Өз backend адаптеріңіз.
```

Жоғарыдағы `storage` — backend орнына қойылатын адаптер мысалы; бұл модульде storage сервері жоқ. `AnalysisError` нақты `code`, `message`, `retryable` атрибуттарын береді. HTTP статусы мен сақтау саясатын backend анықтайды.

Кіріс: `AnalysisInput`; шығыс: `AnalysisResult`; нұсқа: **1.0.0**. `contracts/openapi.json` SHA-256:

```text
b8b529d5e9840dcdcda42d91df6359e4584ddea84cdedea17020d7a55dfc8fe9
```

Түпкі `.gitattributes` келісім файлының нақты байттарын сақтайды. Оны көшіргенде немесе Docker build жасағанда JSON-ды қайта форматтамаңыз: операциялық жүйеге байланысты жол соңы өзгерсе, hash тексеруі тоқтайды.

Парсер `raw_text` түпнұсқасын, бірегей span ID-лерді және тақырып/тыйым контекстін сақтауы тиіс. `span_count` нақты тізімге тең. DOCX беті расталмаса `null`. `locator.path` — құжат ішіндегі орын, операциялық жүйе файлының жолы емес. `pending` кіріс өңделмейді; толық оқылмаған материал `partial`/`failed` деп беріледі.

## 6. Қазылар қайталай алатын тексеру

### API-сыз инженерлік тесттер

```powershell
.\.venv\Scripts\python.exe -m evaluation.check
```

Бұл команда 32 тестті, соның ішінде 15 домендік бақылау сценарийін іске қосады және `evaluation/local_reports/engineering_checks.json` жазады. Модельдің орнына ашық көрсетілген scripted test double қолданылады. **Бұл нәтиже нақты AI дәлдігі болып саналмайды.** Тест double public `analyze` арқылы қолданылмайды.

Қосымша код тексеруі:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ai_engine/requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check --no-cache ai_engine evaluation
.\.venv\Scripts\python.exe -m ruff format --check --no-cache ai_engine evaluation
```

PR үшін Ubuntu/Python 3.11 және Windows/Python 3.12 GitHub Actions workflow қосылған. Оның нақты орындалу мәртебесін PR checks ішінен қараңыз; workflow файлының болуы тесттің серверде өткені деген сөз емес.

Кірісті API-сыз тексеру:

```powershell
.\.venv\Scripts\python.exe -m ai_engine --input evaluation/fixtures/transfer.input.json --validate-only
```

### Бір нақты AI талдауы

```powershell
.\.venv\Scripts\python.exe -m ai_engine --env-file ai_engine/.env --input evaluation/fixtures/transfer.input.json --output evaluation/local_reports/transfer.result.json
```

Күтілетін нәтиже: мұрағаттау міндеті жаңа бөлімшеде табылып, `transferred` белгісі болады; ол ұйым деңгейінде жоғалу болып көрсетілмейді. Нақты нәтиже мен сілтемелерді ашып тексеріңіз.

### Нақты модельді бағалау

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --live --env-file ai_engine/.env --output-dir evaluation/local_reports --max-total-calls 120
```

Әдепкі алты жағдай: өзгеріссіз, жоғалу, ауысу, қайталану, ресми қайта атау, орындаушы/бақылаушының дұрыс бөлінуі. Барлық 15 жағдай үшін `--all` қосылады. Бағалау API кредитін жұмсайды; жалпы сұрау лимиті әр жағдай басталғанда тексеріліп, қалған лимит provider-ге беріледі.

`live_evaluation.json` нақты модель, prompt нұсқасы, usage, уақыт, passed checks, source pair бойынша risk precision/recall көрсетеді. Нөлдік denominator кезінде метрика `null`, автоматты 100% емес. Күтілетін жауаптар тек бағалаушыда пайдаланылады; модельге жіберілмейді. Шағын синтетикалық жиындағы нәтиже жаңа құжаттардағы сапаға кепіл бермейді.

CLI шығу кодтары: `0` — completed/валидті кіріс; `2` — қате; `3` — partial нәтиже сақталды; `130` — пайдаланушы тоқтатты. Evaluation runner: `1` — кемінде бір қабылдау тексеруі өтпеді.

## 7. Деректер және сыртқы сервистер

Git ішіндегі `evaluation/fixtures/` — синтетикалық деректер. Ұйымдастырушының түпнұсқа DOCX файлдары репозиторийге енгізілмеген. Олардың толық және қысқа тексеру кірістері тек жергілікті жұмыс материалында дайындалды.

- OpenAI: `https://api.openai.com/v1/responses`, strict JSON Schema, `store=false`. [Structured Outputs құжаты](https://developers.openai.com/api/docs/guides/structured-outputs).
- NVIDIA қосылғанда: `https://integrate.api.nvidia.com/v1/embeddings`, passage/query режимдері. [Модель құжаты](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2).
- Берілген мәтіндер осы сервистерге талдау үшін жіберіледі. Кілттер браузерге және нәтиже JSON-ға берілмейді.
- NVIDIA істемесе, диагностика беріледі және кейінгі барлық функцияны OpenAI арқылы салыстыру жалғасады.

## 8. Шектеулер және ақауды түсіндіру

1. Нақты API интеграциясы мен модель сапасы кілтсіз тексерілген жоқ; current engineering report мұны ашық көрсетеді.
2. Қайталану/қақтығыс кандидаттары лексика және қосылса embeddings арқылы таңдалады. Синонимдер/тіл айырмашылығы іріктеуден тыс қалуы мүмкін. «Қауіп табылмады» толық қауіпсіздік дәлелі емес.
3. Бөлімше атаулары, рөлдер және күрделі иерархияны LLM қате түсінуі мүмкін; екі AI тексеруі өзара тәуелсіз мамандардың тексеруін алмастырмайды.
4. Құрылымдық қайта ұйымдастыруды іздеуде орысша/қазақша кілт сөздері қолданылады. Атау сәйкестігі мен нақты мәтін бойынша көрсетілген өзгерістер құжаттар ауқымында түсіндіріледі.
5. Парсердегі context сапасы өте маңызды. Код соңғы бірнеше жолды қоса береді, бірақ ұзақ бөлімнің жоғалған тақырыбын толық қалпына келтіретініне кепіл жоқ.
6. Бір талдауда әдепкі 100 API әрекеті, 600 секунд, 1 200 000 кіріс таңбасы және 1500 функция шегі бар. Көлем үнсіз кесілмейді. Толық тексерілмеген жағдай `partial`/`unknown` немесе түсінікті қате болады.
7. Кэш тек бір талдау объектісінің өмірінде сақталады. Тұрақты дерекқор/көп серверлік budget есептегіші жоқ. `usage` долларлық баға емес; белгісіз токен шығыны `null`.
8. Async тоқтату жаңа сұрауларды тоқтатады. Басталып кеткен urllib сұрауы қысқа thread ішінде request timeout-қа дейін аяқталуы мүмкін; оның провайдердегі шығыны жойылмайды.
9. Заңнаманы сырттан іздеу, benchmark, OCR, deployment және UI бұл модульде іске асырылмаған.

Негізгі диагностика: `OPENAI_KEY_MISSING`, `OPENAI_MODEL_MISSING`, `PROVIDER_AUTH`, `PROVIDER_REQUEST_REJECTED`, `MODEL_OUTPUT_TRUNCATED`, `REQUEST_BUDGET_EXCEEDED`, `ANALYSIS_TIMEOUT`, `CONTRACT_MISMATCH`. Құпия сұрау/жауап денесі error мәтінінде шығарылмайды.

## 9. Deployed нұсқа

Бұл AI модулінің бөлек deployed интерфейсі жоқ. Біріктірілген өнімнің сілтемесін backend иесі түпкі README-ге нақты deployment болғаннан кейін қосады.
