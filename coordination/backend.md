# Backend дайындық есебі

2026-09-23 · Qurylym AI · API 1.0.0

## Қорытынды

Backend жергілікті ортада іске қосылды және командамен біріктіруге дайын. Нақты AI/Frontend және Docker арқылы толық өнімнің live дайындығы **әлі расталмаған**. Алғашқы кезеңде GitHub авторизациясы болмаған. Кейін `I0ve33` аккаунтының push құқығы расталып, `team/backend` жеткізілімі main commit `768f483d17242f8b004d091a299177899936bcb6` негізіне дайындалды. Жеткізілім commit-і GitHub тармақ тарихында көрсетіледі.

## Жасалғаны

- Келісімдегі барлық 11 API жолы (GET/POST/PATCH), қатаң Pydantic модельдері және бірізді Error жауабы.
- DOCX/PDF/XLSX оқу; бастапқы bytes/хэш/source/context/locator; графика, формула, бос және оқылмаған мазмұн диагностикасы.
- SQLite: analyses, analysis_versions, documents, sources, results, reviews, jobs, idempotency. Нұсқа өзгерісі мен жазбалар атомарлы сақталады.
- Бір active job; қатар келген сұрауларды ажырату; idempotency; таймаут; restart recovery; бір DATA_DIR-ға бір worker құлпы.
- Парсер/AI жеке процесте; қалыпты runtime-да fake engine жоқ. Схема, дереккөздер, нұсқалар, coverage арифметикасы және summary сілтемелері тексеріледі.
- Сессия оқшаулауы, optional access token, CORS/Origin, body/file/ZIP/XML шектері, HTML escaping/CSP, CSV формула қорғанысы.
- Қазақша сервер беті, баспаға бейімделген HTML есеп, CSV, Docker/Compose, 11 бөлімдік README, 6 жасанды құжат және GitHub handoff нұсқаулығы.

## Нақты орындалған тексерулер

Орта: Windows, Python 3.14.0. Тесттер `-W error` режимінде — ескертулер де қате саналады.

| Тексеру | Нәтиже |
|---|---|
| `python -m backend.scripts.verify` | pip check, Ruff lint/format және **84/84 тест өтті** |
| Соңғы негізгі pytest жүгіруі | **84 passed, 14.57 s**, 0 қате/ескерту |
| Жаңа `.verify-venv` + pinned requirements | Бөлек таза Python ортаға орнатылды; **84/84 тест өтті** |
| Statement coverage | **992 / 1096 = 90.51%**; generated models есептен шығарылған |
| `pip-audit` (жаңартудан кейін) | **No known vulnerabilities found**; бұл 0-day/қолданба қатесі жоқ деген кепіл емес |
| Нақты uvicorn HTTP smoke | health → before/after upload → parser process → original download → SHA-256 өтті |
| Runtime AI жоқ жағдай | `engine_unavailable`; fake нәтиже қайтарылмағаны тексерілді |
| Түпкі MANIFEST хэштері | Бастапқы пакет файлдары өзгертілмеген |

Негізгі толық adapter тесті: upload → тестке енгізілген engine → валидтелген result → source/context → түпнұсқа → review → HTML/CSV → қайта ашылған DB. Сонымен қатар нақты subprocess импорт жолы жасанды тест модулімен тексерілді. Бұл **нақты провайдер/AI сапасын өлшеу емес**.

Қамтылған ақаулар: бүлінген/бос/ескі форматтағы файл, XML entity, ZIP лимиті, PDF шифры/мәтінсіз бет, Excel формуласы, қайталанған жүктеу, бірнеше multipart файл, артық өрістер, stale revision, foreign session/source/file, қатар келген run, engine exception/timeout, қате evidence/санақ, loop parent, аяқталмаған job, HTML/CSV injection, path traversal және frontend asset fallback.

Алғашқы аудит Python орнатқышының ескі `pip 25.2` нұсқасында белгілі осалдықтар тапты; virtualenv `pip 26.2.1`-ге жаңартылды және аудит қайта өтті. DB initialize ішіндегі ашық connection жабылды. Таза орта тесті DOCX ZIP уақыт белгісіне тәуелді тест қатесін анықтады; тест бірдей bytes-ты қайта пайдаланатындай түзетілді. Қателер жасырылған жоқ, қайталап тексерілді.

Жергілікті machine-readable дәлелдер: `backend/test-results/junit.xml`, `clean-junit.xml`, `coverage.json`, `audit.json`, `live-smoke.json`. Олар gitignore ішінде; қорытынды осы есепте сақталған.

## Файлдар

`backend/app/**`, `backend/tests/**`, `backend/scripts/**`, `backend/requirements*.txt`, `backend/pyproject.toml`, `backend/HANDOFF.md`; root `Dockerfile`, `compose.yaml`, `.env.example`, `README.md`, `.gitignore`, `.dockerignore`; `coordination/backend.md`, `coordination/requests/backend.md`.

Толық SHA-256 тізімі жеткізілімнің `backend/delivery/manifest.json` файлында. ZIP тек осы рөлдің файлдарын қамтиды. Frontend, AI және contracts өзгертілмеген.

## Қалған қабылдау жұмысы

### GitHub-қа дайындау кезіндегі интеграция тексеруі

Main `768f483d17242f8b004d091a299177899936bcb6` көшірмесінде backend және AI тесттері бірге іске қосылды. Backend summary validator-ына бұрын тек mapping/finding ID рұқсат етілген; команданың қозғалтқышы дәлелденген unit_change ID-ларын да қайтарады. Validator осы үш нақты нәтиже түрін қабылдайтындай түзетілді; белгісіз ID әлі қабылданбайды. Қозғалтқыштың 15 бақылау сценарийінің нәтижесін backend validator-ымен тексеретін тест қосылды. API келісімі мен AI/frontend коды өзгертілмеді.

AI public error code-тарының бас әріптері сақталады; engine жоқтығының тесті ортақ репозиторийде де дұрыс оқшауланады. Backend dev `jsonschema==4.25.1` AI requirements-пен сәйкестендірілді. Бірлескен нақты нәтиже: **131 тест және 42 subtest өтті**, `-W error`, API кілтісіз scripted provider. Бұл live модель сапасын бағалау емес.

### Келесі қадамдар

1. `team/backend` тармағын командада қарап, main-ге біріктіру. Main-дегі AI/frontend/contracts файлдары өзгертілмейді.
2. Нақты `ai_engine` + API кілттерімен `python -m backend.scripts.smoke --require-engine`.
3. Frontend build-пен толық браузерлік сценарий және визуалды QA. Қолда бар CUA құралдары браузер таба алмады; `iab` unavailable.
4. Docker build/Compose: Docker бұл компьютерде жоқ, сондықтан орындалмады.
5. №8/№9 түпнұсқалары және AI сапасының тәуелсіз positive/negative бақылаулары. Precision/recall, нақты құжаттағы уақыт/құн өлшенген жоқ.

Күрделі Word numbering restart/field, OCR, SmartArt және барлық кесте семантикасына толық қолдау мәлімделмейді. Review note-ты қайта алу және құжатты жою API келісімінде жоқ; ұсыныстар [requests/backend.md](requests/backend.md) ішінде. Қоғамдық production-ға арналған көп пайдаланушы рөлдері, retention және жүктеме тесті жасалған жоқ.
