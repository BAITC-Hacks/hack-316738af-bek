"""Disposable processes keep blocking parsers/providers outside the API event loop."""

import asyncio
import importlib
import inspect
import multiprocessing
import os
import re
import time

from .errors import APIError
from .models import AnalysisInput, ProgressEvent
from .parsers import RejectedFile, parse_document
from .validation import validate_result


def _limit_process():
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024**2, 1536 * 1024**2))


def _child(pipe, kind, arguments):
    try:
        _limit_process()
        if kind == "parse":
            result = parse_document(*arguments)
        else:

            async def work():
                engine = importlib.import_module("ai_engine.pipeline").analyze

                async def emit(event):
                    pipe.send(("progress", ProgressEvent.model_validate(event).model_dump()))

                return await engine(arguments[0], emit_progress=emit)

            result = asyncio.run(work())
        pipe.send(("result", result))
    except RejectedFile as exc:
        pipe.send(
            (
                "error",
                {
                    "code": str(exc),
                    "message": "Файл бұзылған, шифрланған немесе қауіпсіз өңдеу шегінен асады.",
                    "retryable": False,
                },
            )
        )
    except BaseException as exc:
        # Provider exceptions can contain secrets, prompts and uploaded material.
        code, retryable = ("engine_failed" if kind == "engine" else "parse_failed"), True
        if kind == "engine":
            try:
                error_type = importlib.import_module("ai_engine.errors").AnalysisError
                if isinstance(exc, error_type):
                    public_code = getattr(exc, "code", "")
                    if isinstance(public_code, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", public_code):
                        code = public_code
                    retryable = bool(getattr(exc, "retryable", False))
            except (ImportError, AttributeError):
                pass
        pipe.send(
            (
                "error",
                {
                    "code": code,
                    "message": "Өңдеу аяқталмады. Файлды/AI конфигурациясын тексеріп, қайта көріңіз.",
                    "retryable": retryable,
                },
            )
        )
    finally:
        pipe.close()


async def run_process(kind, arguments, timeout, on_progress=None):
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(sender, kind, arguments), daemon=True)
    process.start()
    sender.close()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if receiver.poll():
                try:
                    event, value = await asyncio.to_thread(receiver.recv)
                except EOFError:
                    break
                if event == "result":
                    return value
                if event == "error":
                    raise APIError(400 if kind == "parse" else 500, **value)
                if event == "progress" and on_progress is not None:
                    await on_progress(value)
            elif not process.is_alive():
                break
            await asyncio.sleep(0.02)
        else:
            raise APIError(
                400 if kind == "parse" else 500,
                "parse_timeout" if kind == "parse" else "analysis_timeout",
                "Өңдеу уақытының шегі аяқталды. Құжат көлемін азайтып, қайта көріңіз.",
                True,
            )
        raise APIError(500, "worker_failed", "Өңдеуші процесс тоқтады. Қайта көріңіз.", True)
    finally:
        if process.is_alive():
            process.terminate()
        await asyncio.to_thread(process.join, 3)
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 1)
        receiver.close()
        process.close()


def require_engine():
    try:
        spec = importlib.util.find_spec("ai_engine.pipeline")
    except (ModuleNotFoundError, ValueError):
        spec = None
    if spec is None:
        raise APIError(
            500, "engine_unavailable", "AI қозғалтқышы қосылмаған. ai_engine.pipeline модулін біріктіріңіз.", True
        )


class JobRunner:
    def __init__(self, store, settings, engine=None):
        self.store, self.settings, self.engine = store, settings, engine
        self.tasks = set()

    def start(self, job_id, payload):
        task = asyncio.create_task(self._run(job_id, payload))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, job_id, payload):
        async def emit(event):
            event = ProgressEvent.model_validate(event).model_dump()
            if event["total"] is not None and event["processed"] > event["total"]:
                raise ValueError("invalid_progress")
            # Ignore arbitrary provider text; it may expose upstream error details.
            messages = {
                "extracting": "Функциялар шығарылуда.",
                "matching": "Функциялар салыстырылуда.",
                "verifying": "Дәлелдер тексерілуде.",
            }
            event["message"] = messages.get(event["stage"], "Талдау орындалуда.")
            await asyncio.to_thread(self.store.update_progress, job_id, event)

        try:
            AnalysisInput.model_validate(payload)
            if self.engine is None:
                raw = await run_process("engine", (payload,), self.settings.analysis_timeout, emit)
            else:
                # Injection is exclusively an application-factory seam for tests.
                require = inspect.iscoroutinefunction(self.engine)
                if not require:
                    raise TypeError("Test engine must be async")
                raw = await asyncio.wait_for(self.engine(payload, emit_progress=emit), self.settings.analysis_timeout)
            result = await asyncio.to_thread(validate_result, payload, raw)
            await asyncio.to_thread(self.store.finish, job_id, result)
        except asyncio.CancelledError:
            await asyncio.to_thread(
                self.store.finish,
                job_id,
                error={
                    "code": "server_shutdown",
                    "message": "Сервер тоқтатылды. Талдауды қайта бастаңыз.",
                    "retryable": True,
                },
            )
            raise
        except APIError as exc:
            await asyncio.to_thread(self.store.finish, job_id, error=exc.body)
        except TimeoutError:
            await asyncio.to_thread(
                self.store.finish,
                job_id,
                error={
                    "code": "analysis_timeout",
                    "message": "Талдау уақыты аяқталды. Қайта көріңіз.",
                    "retryable": True,
                },
            )
        except Exception:
            await asyncio.to_thread(
                self.store.finish,
                job_id,
                error={
                    "code": "invalid_engine_result",
                    "message": "AI нәтижесі келісім не дәлел тексеруінен өтпеді. Қозғалтқышты тексеріңіз.",
                    "retryable": True,
                },
            )

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
