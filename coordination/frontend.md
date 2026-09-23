# Qurylym AI — frontend дайындық есебі

Тексерілген күн: **2026-09-23**. Рөл: frontend. API: **1.0.0**.

## Нәтиже

Frontend іске асырылды және жергілікті production жинағында тексерілді. Қазақша desktop/mobile интерфейс, upload, progress, құрылым/функция/тәуекел нәтижелері, source панелі, review және экспорт дайын.

**31 unit/API тест + 30 браузер тест өтті.** Браузер жиыны — 15 сценарий × 2 профиль: Desktop Chrome (1280×720) және Pixel 7 мобильді эмуляциясы (412×839). Мобильді эмуляция физикалық телефон тестін немесе Safari/Firefox тексеруін алмастырмайды.

Бұл — frontend және HTTP келісімін имитациялау тексеруі. Нақты backend/AI, нақты құжат парсерлері және модель сапасы тексерілген жоқ.

## Git және файл шекарасы

- Әзірлеу папкасы Git репозиторийі емес; жеткізу көшірмесі `frontend/.tools/github-repository` ішінде.
- Берілген remote: `https://github.com/BAITC-Hacks/hack-316738af-bek.git`.
- Алғашқы `Repository not found` себебі басқа сақталған аккаунт болған. Пайдаланушы `Aslanxz008` аккаунтымен GitHub кіруін растады; жеке репозиторий ашылды.
- Frontend тармағы: `team/frontend`. Негізі — `main` тармағының `d442e9ff6274cbc4c2e1da04a7a8a46aef06c72d` commit-і.
- `team/ai-engine` тармағындағы API келісімі оқылып, frontend келісімімен салыстырылды; SHA-256 бірдей. Main ішінде contracts әлі жоқ, оларды ортақ біріктіру кезінде AI тармағынан қосу қажет.
- Жеткізу commit-і мен қашықтағы тармақ төмендегі жеткізу жазбасында көрсетіледі.
- Өзгерістер тек `frontend/**`, `coordination/frontend.md`, `coordination/requests/frontend.md` ішінде. Backend, AI, contracts, түпкі README/Docker өзгертілмеді.
- Келісім SHA-256 өзгермеген: `b8b529d5e9840dcdcda42d91df6359e4584ddea84cdedea17020d7a55dfc8fe9`.

## Нақты орындалған тексерулер

Орта: Windows, portable Node **22.23.2**, npm **10.9.8**, Google Chrome **153.0.8010.54**. Node ресми nodejs.org ZIP-інен жүктеліп, ресми SHASUMS256 хэшімен салыстырылды. Portable құралдар `frontend/.tools/` ішінде; Git/тапсыру архивіне кірмейді.

| Команда / тексеру | Нәтиже |
| --- | --- |
| `npm run typecheck` / production build ішіндегі `tsc -b` | Өтті, TypeScript қатесі жоқ |
| `npm test` | 2 файл, **31 тест өтті** |
| `npm run build` | Өтті, `dist/` жасалды |
| `npm run contract:check` | SHA-256, generated типтер, схема және төрт fixture сәйкес |
| `$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:e2e` | **30 тест өтті**, 54.6 секунд |
| axe WCAG 2 A/AA + WCAG 2.1 AA, upload/result/source dialog, desktop/mobile | Тексерілген беттерде автоматты violation жоқ |
| `npm run format:check` | Prettier тексеруі өтті |
| `npm audit --audit-level=low` | **0 белгілі vulnerability** сол сәттегі registry аудитінде |
| Тек бастапқы код пен lock-файл көшірілген бос `.tools/clean-verification`: `npm ci` → `npm run build` | Таза орнату және жинау өтті |
| Desktop/mobile screenshot визуалды тексеруі | Көлденең бет overflow жоқ; мәтін/панельдер оқылады |

`npx playwright install chromium` sandbox ішінде де, желілік рұқсатпен де CDN timeout қатесімен аяқталды. Тесттер орнатылған **нақты Google Chrome** арқылы орындалды; өтпеген тесттерді өтті деп есептеген жоқпыз.

Алғашқы браузер тексеруінде мәтін контрасты және select label сәйкестігі мәселелері табылды. Контраст, қаріп өлшемдері, өріс атаулары түзетіліп, кейін толық жиын қайта өтті. Типтер мен JSON импорттарының tooling мәселелері де түзетілді.

## Браузердегі 15 сценарий

1. Кезекті бірнеше upload → run → polling → source → original download → review + note → HTML/CSV → refresh.
2. Run желісі үзілгенде және бет жаңартылғанда бір Idempotency-Key сақтау.
3. Жоғалу: бос after тізімі; негіздеме; құрылым; мәтіндік және түр сүзгілері.
4. Құжат тобын ауыстыру кезіндегі 409: күйді жаңарту, ескі нәтижені алып тастау.
5. Partial мәртебесі және оқылмаған материал диагностикасы.
6. Бос нәтижелер және функциялар тізімі.
7. Сервер қатесі кезінде live режимін сақтау, demo-ға өтпеу.
8. Source/review қатесі кезінде жалған сәттілік көрсетпеу.
9. Қате формат және 10 файл шегін HTTP сұрауынан бұрын тексеру.
10. Offline explicit demo: белгі, review күйі, HTML экспортында note escape.
11. Жойылған/мерзімі өткен сессия және сәйкес емес API shape.
12. Зиянды HTML source-ты мәтін түрінде көрсету; екі evidence арасында ауысу.
13. Басқа revision-ның нәтижесін қабылдамау.
14. Failed талдау диагностикасы және қайта іске қосу мүмкіндігі.
15. Пернетақта tabs, focus restore, modal Escape, axe және көлденең overflow.

## Жұмыс істейтін UI жолдары

- Live әдепкі: `/`. Development `/api` proxy → `127.0.0.1:8000`.
- Explicit synthetic demo: `/?demo=1` — **«Жасанды demo деректері»** белгісі бар.
- `Салыстыруды бастау` екі топ болғанда іске қосылады; барлық upload кезекпен жүреді.
- `Тәуекелдер` → `Қолдайтын дәлел` → түпнұсқа/контекст → `Шешімді сақтау`.
- `Функциялар` → `Негіздеме` → before/after жауапты жолы → source.
- `Құрылым` → екі баған және әр өзгерістің негізі.
- `Есепке өту` → summary reference → HTML/CSV.
- UI notes/құжат мәтінін raw HTML ретінде қоспайды; demo HTML escape және CSV formula prefix қорғанысы бар. Live экспорт қауіпсіздігі backend міндеті.

## Өзгерген файлдар

- `frontend/package.json`, `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `playwright.config.ts`.
- `frontend/index.html`, `public/favicon.svg`, `.env.example`, `.gitignore`, `.prettierrc.json`, `.prettierignore`, `start.ps1`, `README.md`.
- `frontend/src/App.tsx`, `main.tsx`, `styles.css`.
- `frontend/src/api/{client.ts,client.test.ts,types.ts,schemas.json,validation.ts}`.
- `frontend/src/hooks/useAnalysis.ts`.
- `frontend/src/lib/{domain.ts,domain.test.ts}`.
- `frontend/src/components/{common.tsx,Upload.tsx,Progress.tsx,Results.tsx,EvidencePanel.tsx,Report.tsx}`.
- `frontend/src/demo/provider.ts` және төрт `*.example.json` көшірмесі.
- `frontend/scripts/generate-contract.mjs`, `frontend/tests/app.spec.ts`.
- `frontend/docs/screenshots/` — тексерілген desktop/mobile көріністері.
- `coordination/frontend.md`, `coordination/requests/frontend.md`.

Generated `dist/`, тест есептері, node_modules, portable tools және `output/` Git-ке кірмейді.

## Әділқазы тұрғысынан қабылдау шекарасы

| Қазы тексеретін нәрсе | Frontend дәлелі | Қалған тәуелділік |
| --- | --- | --- |
| Міндет кімге көшті? | Before/after функция жолы, бірнеше өзгеріс белгісі, source | AI дұрыс сәйкестік қайтаруы |
| Жоғалу ма, басқа бөлімшеге ауысу ма? | Бос after дәйексөз жасамайды; іздеу ауқымы ашық | Барлық бөлімшені engine іздеуі |
| Дәлел қайда? | Үзінді, контекст, locator, original download | Backend source/session тұтастығы |
| Адам шешімі сақтала ма? | PATCH, server response, status refresh және экспорт тексерілген | Live DB және export мазмұнын бірлесіп тексеру |
| Құжат оқылмаса ше? | Partial/failed/diagnostics, retry және error UI | Парсердің шынайы диагностикасы |
| Қазы қайта іске қоса ала ма? | Lock-файл, таза npm ci + build, README | Ортақ Docker, backend конфигурациясы және Git remote |

Қазы ұпайы, бірінші орын немесе толық өнімнің қатесіздігі туралы кепіл берілмейді. Frontend өз шекарасында дайын; толық өнімге live интеграциялық қабылдау қажет. Келісімнің note оқу және metadata өңдеу шектеулері requests файлында нақты тіркелген.

## GitHub жеткізуі

- Аккаунт: `Aslanxz008`.
- Тармақ: [team/frontend](https://github.com/BAITC-Hacks/hack-316738af-bek/tree/team/frontend).
- Frontend кодының commit-і: [`26a10196ca0d1a4f4e25967a2fe46f498e5ffc12`](https://github.com/BAITC-Hacks/hack-316738af-bek/commit/26a10196ca0d1a4f4e25967a2fe46f498e5ffc12).
- 44 файл: frontend, оның тесттері/нұсқаулығы және екі coordination есебі. Main, backend және AI тармақтары өзгертілмеді.
- GitHub жұмыс көшірмесінде `npm ci`, `npm run build`, `npm test` қайта орындалды: 31 тест өтті, production жинағы бұрын тексерілген жинақпен сәйкес.
- `frontend/.gitattributes` қосылды; мысалдардың жол аяқталуы генераторда LF-ке келтіріледі. Windows/Linux checkout айырмасы contract тексеруін бұзбайды. Ортақ `contracts/openapi.json` байттары өзгертілмеді.
- Ортақ біріктіру үшін `team/ai-engine` ішіндегі contracts және backend тармағы әлі қажет. Frontend тармағын main-ге біріктіру — командалық интеграция қадамы.
