# Backend-ті командаға беру

Бұл каталог — Qurylym AI backend бөлігі. Келісім **1.0.0**, OpenAPI SHA-256:

```text
b8b529d5e9840dcdcda42d91df6359e4584ddea84cdedea17020d7a55dfc8fe9
```

## Қазір ашу

Репозиторий түбінен:

```powershell
backend\.venv\Scripts\python -m backend.scripts.start
```

http://127.0.0.1:8000 — бастапқы бет; http://127.0.0.1:8000/docs — интерактивті API. Жаңа ортада алдымен README-дегі virtualenv және requirements командаларын орындаңыз. PowerShell script execution policy-ін өзгерту қажет емес: Python командаларын пайдаланыңыз.

## Архив

`backend/delivery/qurylym-backend.zip` — тек backend және оған тиесілі инфрақұрылым файлдары. `frontend/`, `ai_engine/`, `contracts/`, `.env`, DB, түпнұсқа бизнес құжаттары және virtualenv архивке кірмейді. Оған сәйкесті файлдар мен хэштер `backend/delivery/manifest.json` ішінде. Қайта жинау:

```powershell
backend\.venv\Scripts\python -m backend.scripts.package_backend
```

## GitHub-қа салу

GitHub репозиторийі жеке: `BAITC-Hacks/hack-316738af-bek`. Backend тармағы — `team/backend`, аккаунт — `I0ve33`. Жүктеу алдында main commit `768f483d17242f8b004d091a299177899936bcb6` және ортақ келісім хэші тексерілді. Төмендегі командалар — басқа ортадан қайта тапсыру нұсқаулығы; кілт не парольді чатқа жібермеңіз.

1. GitHub аккаунтыңызға қолжетімді репозиторийді Git/GitHub Desktop арқылы clone жасаңыз.
2. Біріктіруші берген baseline commit-ке сүйеніп `team/backend` тармағын ашыңыз. Тармақ бар болса соған ауысыңыз.
3. Архивтің файлдарын **сол clone түбіне** салыңыз. Бұрыннан бар README, Dockerfile, compose, .gitignore/.dockerignore өзгерістерін diff арқылы салыстырыңыз; басқа қатысушылардың өзгерістерін үстінен жоғалтпаңыз.
4. Ортақ `contracts/` хэшінің жоғарыдағы мәнге тең екенін тексеріңіз.
5. README бойынша тәуелділіктерді орнатып, тексеруді іске қосыңыз.

```powershell
git switch -c team/backend BASELINE_COMMIT
backend\.venv\Scripts\python -m backend.scripts.verify
git add backend Dockerfile compose.yaml .env.example README.md .gitignore .dockerignore coordination/backend.md coordination/requests/backend.md
git diff --cached --stat
git diff --cached --check
git commit -m "Implement Qurylym backend contract v1 with parsers and verified exports"
git push -u origin team/backend
```

`BASELINE_COMMIT` орнына біріктірушінің нақты хэшін жазыңыз. Main-ға тікелей push жасамаңыз. Біріктірушіге `git rev-parse HEAD` нәтижесін, тест есебін және [интеграция мәселелерін](../coordination/requests/backend.md) беріңіз.

## Басқа қатысушылармен қосу

- AI: root `ai_engine.pipeline.analyze`; кіріс/шығыс дәл ортақ схема; `emit_progress` async; құжат metadata-сы және ID/revision өзгермейді; жаңа finding review_status=unreviewed.
- Frontend: барлық маршрут `contracts/openapi.json` бойынша; cookies бірге жіберіледі; әр upload-тан соң қайтқан **толық state** қабылданады; жаңа кіріс — жаңа revision.
- Толық integration: сервер іске қосылған соң `python -m backend.scripts.smoke --require-engine`. Бұл нақты AI-ды шақыруы және API кредитін жұмсауы мүмкін.
- Нақты №8/№9 құжаттарында функция ауысуы, жоғалу, тәуекел және дәлел мағынасын команда бөлек тексереді. Backend тесттері бұл AI бағалауын алмастырмайды.
