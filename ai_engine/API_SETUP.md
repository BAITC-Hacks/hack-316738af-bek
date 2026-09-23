# API кілттерін қосу

Бұл нұсқаулық AI модуліне арналған. Кілттерді сервер сақтайды; frontend backend-тің `/api` маршруттарын шақырады.

## 1. Қандай қолжетімділік керек?

| Айнымалы | Міндеті | Қажеттілігі |
|---|---|---|
| `OPENAI_API_KEY` | Функцияларды шығару, салыстыру және дәлелдерді талдау | Міндетті |
| `OPENAI_MODEL` | OpenAI моделінің атауы, бастапқы конфигурация: `gpt-4.1` | Міндетті; бұл кілт емес |
| `NVIDIA_API_KEY` | Функциялар ұқсастығын іздеуге арналған embeddings | NVIDIA қосылса керек |
| `NVIDIA_ENABLED` | NVIDIA сұрауларын қосу: `true` / `false` | Алғашқы тексеруде `false` |
| `NVIDIA_EMBED_MODEL` | `nvidia/llama-nemotron-embed-1b-v2` | NVIDIA қосылса қолданылады |

GitHub қолжетімділігі кодты жүктеуге арналған. GitHub token-ді осы файлға енгізудің қажеті жоқ. OpenAI және NVIDIA — екі бөлек кілт; бірінің кредиті екіншісіне жұмсалмайды.

## 2. Кілттерді алу

### OpenAI

1. Ұйымдастырушының белсендіру нұсқаулығын орындап, хакатон кредиті берілген аккаунт/жобаны пайдаланыңыз. Бұл репозиторий кредитті өзі белсендірмейді.
2. [OpenAI API keys](https://platform.openai.com/api-keys) бетінде жобаға API кілтін жасаңыз немесе ұйымдастырушы берген дайын кілтті қолданыңыз.
3. Кілтті төмендегі жергілікті файлдың `OPENAI_API_KEY=` жолына енгізіңіз. Кілтті чатқа, README-ге немесе screenshot-қа қоспаңыз.

OpenAI ресми нұсқаулығы кілтті жасап, оны сервердің орта айнымалысы арқылы пайдалануды көрсетеді: [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart).

### NVIDIA

1. Хакатонға арналған NVIDIA қолжетімділігін белсендіріңіз.
2. [NVIDIA API Catalog](https://build.nvidia.com/) ішінде модель бетін ашып, **Get API Key** таңдаңыз. Ұйымдастырушы дайын API кілтін берген болса, соны пайдаланыңыз.
3. Кілтті `NVIDIA_API_KEY=` жолына енгізіңіз. NVIDIA-ны нақты қосу үшін `NVIDIA_ENABLED=true` орнатыңыз.

Ресми қадамдар: [NVIDIA API Catalog Quickstart](https://docs.api.nvidia.com/nim/docs/api-quickstart). Қолданылатын embeddings моделі: [NVIDIA модель құжаты](https://docs.api.nvidia.com/nim/reference/nvidia-llama-nemotron-embed-1b-v2).

## 3. Жергілікті файл

Репозиторий түбірінде PowerShell арқылы орындаңыз. Бар файлдың кілттері қайта жазылмайды:

```powershell
if (-not (Test-Path -LiteralPath ai_engine/.env)) {
    Copy-Item -LiteralPath ai_engine/.env.example -Destination ai_engine/.env
}
```

Редактордан **`ai_engine/.env`** файлын ашып, бос кілт жолдарын толтырыңыз. `.env.example` файлын өзгертпеңіз. Екі сервис қосылған конфигурация:

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1
NVIDIA_ENABLED=true
NVIDIA_API_KEY=YOUR_NVIDIA_API_KEY
NVIDIA_EMBED_MODEL=nvidia/llama-nemotron-embed-1b-v2
ANALYSIS_TIMEOUT_SECONDS=600
AI_REQUEST_TIMEOUT_SECONDS=90
AI_MAX_REQUESTS=100
AI_MAX_OUTPUT_TOKENS=12000
AI_CONCURRENCY=3
```

`YOUR_...` — толтыру орны; оны нақты кілтпен ауыстырыңыз. NVIDIA кілті әлі жоқ болса, `NVIDIA_ENABLED=false`, `NVIDIA_API_KEY=` күйінде қалдырыңыз: негізгі талдау OpenAI арқылы жұмыс істейді. `gpt-4.1` осы жобаның бастапқы конфигурациясы; нақты сапасы live бағалаумен тексеріледі.

Кілт файлдары engine `.gitignore` тізімінде. Тексеру:

```powershell
git check-ignore ai_engine/.env
```

Күтілетін жауап: `ai_engine/.env`. Private репозиторийге де кілт жіберілмейді.

## 4. Орнату және тексеру

Python 3.11+ қажет. Барлық команда репозиторий түбірінен орындалады:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ai_engine/requirements.txt
.\.venv\Scripts\python.exe -m ai_engine --env-file ai_engine/.env --config-check
```

`openai_key_present` және `openai_model_present` екеуі де `true` болуы керек. NVIDIA қосылғанда `nvidia_enabled` және `nvidia_key_present` те `true`. Бұл тек мәндердің бар екенін тексереді; кілттің жарамдылығы, модель рұқсаты немесе баланс бұл командамен тексерілмейді. Команда кілттің өзін шығармайды, API кредитін жұмсамайды.

Тегін инженерлік тесттер:

```powershell
.\.venv\Scripts\python.exe -m evaluation.check
```

Нақты OpenAI талдауы, кредит жұмсайды:

```powershell
.\.venv\Scripts\python.exe -m ai_engine --env-file ai_engine/.env --input evaluation/fixtures/transfer.input.json --output evaluation/local_reports/transfer.result.json
```

Күтілетін жағдай: функция басқа бөлімшеге ауысқан, `transferred` белгісі бар; ұйым деңгейінде жоғалу деп көрсетілмеуі тиіс. Алдымен NVIDIA өшірулі болғаны екі сервистің конфигурациясын бөлек тексеруге көмектеседі. NVIDIA қосылғанын тек env белгісімен бағаламаңыз: шағын transfer жағдайында embeddings шақырылмауы мүмкін; нақты шақыру result ішіндегі `usage` арқылы расталады.

Алты бақылау жағдайындағы нақты модель бағасы:

```powershell
.\.venv\Scripts\python.exe -m evaluation.run --live --env-file ai_engine/.env --output-dir evaluation/local_reports --max-total-calls 120
```

Барлық 15 жағдай үшін `--all` қосыңыз. Есеп: `evaluation/local_reports/live_evaluation.json`. Сұрау саны лимиті долларлық шығын лимитіне тең емес. Usage пен қалған кредитті провайдер кабинетінен де бақылаңыз.

## 5. Backend және frontend қалай қосылады?

Backend иесі `ai_engine/requirements.txt` тәуелділіктерін сервер ортасына орнатады және модульмен бірге `contracts/` каталогын жеткізеді. Сервер процесінде жоғарыдағы env айнымалылары болуы керек. Public функция `.env` файлын автоматты оқымайды:

```python
from ai_engine.pipeline import analyze
from ai_engine.errors import AnalysisError

result = await analyze(parsed_input, emit_progress=save_progress)
```

`parsed_input` — бекітілген `AnalysisInput`, `save_progress` — async callback, нәтиже — `AnalysisResult`. Backend кілттерді өзі оқитын `.env` конфигурациясынан немесе Docker `env_file` арқылы процеске береді. Backend файлының нақты орны оның README-сінде көрсетіледі; `ai_engine/.env` файлының жай ғана болуы серверге мәндерді жүктемейді. Айнымалылар өзгерсе, серверді қайта іске қосыңыз.

Frontend-ке OpenAI/NVIDIA кілттері берілмейді. Қажет local dev баптауы — `VITE_API_BASE_URL`; онда тек backend адресі болады. `VITE_OPENAI_API_KEY` сияқты құпия айнымалы жасамаңыз.

Deployment кезінде кілттер backend қызметінің environment/secrets баптауына енгізіледі. Қазіргі GitHub Actions тесттері AI кілттерін қолданбайды; GitHub Secrets-ке кілтті қосу өздігінен қолданбаны баптамайды.

## 6. Жиі кездесетін жағдайлар

| Белгі | Тексеру |
|---|---|
| `OPENAI_KEY_MISSING` | Дұрыс `.env` жолын, толтырылған мәнді және серверге жүктелуін тексеріңіз |
| `OPENAI_MODEL_MISSING` | `OPENAI_MODEL=gpt-4.1` немесе қолжетімді үйлесімді модель орнатыңыз |
| `PROVIDER_AUTH` | Кілттің дәл көшірілгенін және тиісті аккаунт/жобаға тиесілі екенін тексеріңіз |
| `PROVIDER_REQUEST_REJECTED` | Модель рұқсатын, сұрау сәйкестігін және провайдер кабинетінің күйін тексеріңіз |
| `REQUEST_BUDGET_EXCEEDED` / `ANALYSIS_TIMEOUT` | Кіші бақылау кірісінен бастаңыз; толық құжатқа лимитті бағалап өзгертіңіз |
| `.env` өзгерді, нәтиже өзгермеді | Бар process env мәндері файлдан басым; сервер/терминал конфигурациясын тексеріңіз |

Нақты API тексеруі аяқталмағанша кілттердің жұмыс істейтінін және модель сапасын расталды деп белгілемеңіз. Backend/frontend біріктірілгенде Word/PDF/Excel → талдау → дәлел → review → export сценарийі бөлек тексеріледі.
