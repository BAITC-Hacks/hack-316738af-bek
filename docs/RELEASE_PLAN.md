# Біріктіру, тексеру және Render-ге жариялау

## 1. Команданың келесі қадамы

Үш бөлік бір репозиторийде: `ai_engine/`, `backend/`, `frontend/`. Backend PR №3, frontend PR №2 және AI PR №1 негізгі тармаққа біріктірілген. Біріктіруші ақауларды `integration/live-validation` тармағында түзетеді. Команда қосымша өзгерістерін шағын commit/PR арқылы береді; соңғы қабылдауға арналған main бір нұсқа ретінде бекітіледі.

Ешкім жобаны нөлден қайта құрастырмайды. Түзетілген тармақтың PR-ы main-ға қосылады, одан кейін дәл сол commit серверге орналастырылады. API келісімі 1.0.0 және оның SHA-256 мәні сақталады.

## 2. Қабылдау реті

| Кезең | Міндетті тексеру | Өту дәлелі |
|---|---|---|
| Орнату | Бір ортаға backend + AI dependencies, npm ci/build | pip check, жұмыс істейтін жинақ |
| Модульдер | Backend API/парсер/DB, AI, frontend unit тесттері | Нақты test report |
| Браузер | Desktop/mobile, қате/partial, retry, source, review | 30 HTTP имитациясы бар Playwright сценарийі |
| Нақты AI | Жоғалу, ауысу, қайталану, қайшылық, қайта атау, жауапсыз міндет және қалған бақылаулар | Live 15 жағдай, нақты usage және source сәйкестігі |
| Толық байланыс | Браузер → DOCX → backend → OpenAI → evidence → review → export | Имитациясыз live browser/HTTP сценарийі |
| Ұйымдастырушы дерегі | №8/№9, §3.4, §5.4.4 → §5.3.3, §5.8 тыйымдары | Қолмен семантикалық тексеру және шектеулер |
| Жариялау | Docker build, Render startup/health/login, дәл сол live сценарий | HTTPS URL, build commit, экспорт |
| Тапсыру | README 11 бөлімі, нұсқа, код, URL, қысқа демо | Платформадағы «Шешімді тапсыру» мәртебесі |

Табылған ақау үшін: қайталату жолын сақтау → түзету → сол жағдайды қайта тексеру → әсер ететін регрессия жиынын өткізу. Ішінара нәтиже, орындалмаған тексеру немесе қате тест табысты нәтиже болып саналмайды.

## 3. Қайталанатын командалар

README бойынша `backend/.venv` ортасын орнатыңыз. Командалар репозиторий түбірінде:

```powershell
backend\.venv\Scripts\python -m backend.scripts.verify
backend\.venv\Scripts\python -m evaluation.check
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
npm.cmd run contract:check --prefix frontend
```

Браузер орнату/тексеру:

```powershell
Set-Location frontend
npx.cmd playwright install chromium
npm.cmd run test:e2e
Set-Location ..
```

Орнатылған Edge қолданылса `PLAYWRIGHT_CHANNEL=msedge` орнатылады. Бұл Chrome/Safari/Firefox толық үйлесімділігі тексерілді дегенді білдірмейді.

Нақты AI, API кредитін жұмсайды:

```powershell
backend\.venv\Scripts\python -m evaluation.run --live --all --env-file .env --output-dir evaluation/local_reports/live --max-total-calls 180
```

Сервер бір терминалда: `backend\.venv\Scripts\python -m backend.scripts.start`. Басқа терминалда:

```powershell
backend\.venv\Scripts\python -m backend.scripts.smoke --require-engine --fixture-set judge
```

Нақты браузер сценарийі `frontend/integration/live.spec.ts` ішінде. Launcher жергілікті `.env` файлынан кіру кодын оқиды; OpenAI/NVIDIA кілттерін браузерлік тест процесіне бермейді. Тест нақты AI кредитін жұмсайды:

```powershell
backend\.venv\Scripts\python -m backend.scripts.live_browser --url http://127.0.0.1:8000 --channel msedge --fixture-set judge
```

Орнатылған Playwright Chromium қолданылса `--channel msedge` параметрін алып тастаңыз. Сервердегі тексеруде `--url` мәнін нақты HTTPS адресімен ауыстырыңыз; жергілікті `.env` ішіндегі кіру коды сервердің `APP_ACCESS_TOKEN` мәніне сәйкес болуы керек. API кілттері серверде қалады.

## 4. Render: ұсынылған тегін демо

Бір **Docker Web Service** frontend жинағын және FastAPI-ды бір origin-де ұсынады. `render.yaml` осы конфигурацияны сипаттайды. Атауы бос болса `qurylym-ai.onrender.com` тәрізді адрес беріледі; нақты URL тек сервис құрылғанда белгілі болады. Бөлек домен сатып алу талап етілмейді. [Render Docker](https://render.com/docs/docker), [FastAPI жариялау](https://render.com/docs/deploy-fastapi).

1. Render аккаунтына кіріңіз. GitHub-ты Render-ге бөлек қосып, **BAITC-Hacks/hack-316738af-bek** private репозиторийіне рұқсат беріңіз. Codex-тегі GitHub қолжетімділігі Render-ге автоматты көшпейді. Repo тізімде болмаса ұйым әкімшісінен Render қолданбасына рұқсат сұрау қажет болуы мүмкін. Репозиторийді public етпеңіз. [Git провайдерін қосу](https://render.com/docs/git-provider).
2. GitHub-тағы соңғы тексерілген `main` commit-ін таңдаңыз. Build/deploy бетінде дәл сол commit тұрғанын тексеріңіз.
3. **New → Blueprint** арқылы осы repo мен `render.yaml` таңдаңыз. Балама: **New → Web Service**, Language **Docker**, branch **main**, Dockerfile **./Dockerfile**, Health Check **/api/health**, plan **Free**. Root directory — репозиторий түбірі.
4. `OPENAI_API_KEY` мәнін Render Environment-ке енгізіңіз. `OPENAI_MODEL=gpt-4.1`. `APP_ACCESS_TOKEN` — API кілтінен бөлек ұзын кездейсоқ кіру коды; оны қазыларға жеке бересіз. `COOKIE_SECURE=true`. NVIDIA дайын болмаса `NVIDIA_ENABLED=false`. Web Service-ті қолмен құрсаңыз, `render.yaml` ішіндегі барлық Environment мәндерін көшіріңіз: `ANALYSIS_TIMEOUT_SECONDS=900`, `AI_REQUEST_TIMEOUT_SECONDS=120`, `AI_MAX_REQUESTS=300`, `AI_MAX_OUTPUT_TOKENS=20000`, `AI_CONCURRENCY=3`, `AI_MAX_RISK_PAIRS=200`, `DATA_DIR=/data`. Blueprint оларды өзі орнатады.
5. Blueprint-тағы `FORWARDED_ALLOW_IPS=*` тек Render-дің reverse proxy артындағы сервиске арналған. Тікелей интернетке ашылған жеке серверде тек нақты сенімді proxy IP-лерін беріңіз.
6. Docker `PORT` айнымалысын қолдайды. Бір worker ғана іске қосылады. Кілттер Dockerfile-ға, frontend build-ке немесе GitHub-қа енгізілмейді.
7. Build log → startup log → `/api/health` тексеріңіз. Жаңа браузерде `/access` арқылы кіріп, екі synthetic DOCX-ті жүктеп, талдау/дәлел/review/export жолын қайталаңыз. Қазыларға берілетін URL осыдан кейін README мен тапсыру формасына қосылады.

`autoDeployTrigger: "off"` өзгеріп жатқан main әр commit сайын демоны қайта іске қоспауы үшін берілген. Кейін жаңа тексерілген commit-ті **Manual Deploy** арқылы жаңартыңыз. Бұл GitHub-тағы test gate-ті өтті деп белгілемейді. [Render deploys](https://render.com/docs/deploys), [Blueprint өрістері](https://render.com/docs/blueprint-spec).

## 5. Free нұсқаның шегі

Render Free 15 минут кіріс трафик болмаса ұйқыға кетеді; келесі ашылуы шамамен бір минут алады. Restart/redeploy/spin-down кезінде жергілікті файлдар мен SQLite жоғалады. Тегін Web Service-ке persistent disk қосылмайды. [Render Free шектеулері](https://render.com/docs/free).

Сондықтан бұл конфигурация **уақытша хакатон демосы**: әр тексеруде құжаттарды қайта жүктеуге болады, қорытындыны HTML/CSV ретінде жүктеп алу қажет. Демода сақтау шегі ашық көрсетіледі; ұзақ мерзімді сақтау іске асырылды деп айтылмайды. Тұрақты сақтау үшін бөлек сыртқы дерекқор/файл қоймасы немесе persistent disk бар тариф қажет; бұл өзгеріс әзірге іске асырылмаған. Free сервер жадының нақты жеткіліктілігі deployment үстінде тексеріледі.

## 6. Қорғау және соңғы тапсыру

- 20 секунд: кімнің қандай мәселесін шешеміз.
- 40 секунд: before/after жүктеу және бөлімше өзгерісі.
- 60 секунд: функцияның ауысуы, жоғалу/қайталану мысалы және екі дереккөз.
- 40 секунд: қақтығыс шарты, қызметкер шешімі және экспорт.
- 30 секунд: live тексеру нәтижесі, шектеулер, қайта іске қосу командасы және URL.

Қазылардың критерийінде deployment үшін бөлек бекітілген ұпай жоқ. Жұмыс істейтін URL шешімді тексеруді жеңілдетеді; негізгі салмақ міндетті сценарий, техникалық сапа және README/қайта іске қосуда. Дедлайнға дейін GitHub push жеткіліксіз: платформада кейсті таңдап, «Шешімді тапсыру» батырмасымен атау/сипаттама/сілтемелерді жіберу қажет.

## 7. Render-ді команда орнатады

Жергілікті `.env` GitHub-қа жіберілмейді. Render-ге кілт пен кіру кодын өзіңіз енгізесіз. GitHub-та жаңа түзету қосылған соң **Manual Deploy → Deploy latest commit** орындаңыз. Тек **Live** мәртебесі жеткіліксіз: жаңа браузерде кіру, бақылау DOCX жұбы, нақты AI нәтиже және экспортты тексеріңіз. Нақты URL мен кіру кодын қазылардың тапсыру формасына беріңіз; API кілтін бермеңіз.
