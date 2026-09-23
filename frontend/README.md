# Qurylym AI интерфейсі

React 19 / TypeScript / Vite 8. Құжаттарды жүктеу, талдау кезеңдері, құрылым мен функциялар, тәуекелдер, дәлел панелі, қызметкер шешімі және экспорт.

## Әзірлеу

```sh
cd frontend
npm ci
npm run dev
```

Vite `/api` сұрауларын `http://127.0.0.1:8000` backend-іне бағыттайды. Сервер бөлек іске қосулы болуы керек. Production-та `npm run build` жасаған `dist/` жинағын FastAPI бір origin-нен ұсынады.

## Тексеру

```sh
npm test
npm run build
npm run contract:check
npx playwright install chromium
npm run test:e2e
```

`tests/` HTTP жауаптарын имитациялайды; `integration/live.spec.ts` нақты backend және AI арқылы тексереді. Орнатылған Edge үшін `PLAYWRIGHT_CHANNEL=msedge` қолданылады. Толық нұсқаулық пен нақты нәтижелер: [README](../README.md), [тексеру есебі](../docs/VERIFICATION.md).

## Маңызды келісімдер

- API: 1.0.0; AJV жауап схемасын тексереді.
- OpenAI/NVIDIA кілттері frontend-ке берілмейді; `VITE_*` айнымалылары ашық жинаққа кіреді.
- Demo режимі жасанды деректі анық белгілейді. Нақты API қатесі демомен ауыстырылмайды.
- Қызметкер шешімі серверде сақталады; бұрынғы түсініктеме есептен оқылады. Форманы қайта сақтау түсініктемені алмастырады.
- Source мәтіні HTML ретінде орындалмайды. Қамту санақтары AI дәлдігінің пайызы емес.
