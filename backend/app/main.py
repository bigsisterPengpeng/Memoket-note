"""FastAPI application lifecycle, request locale, local service health and packaged frontend hosting."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
import os
import pathlib

import httpx
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import backup, store
from .database.ingest import asr
from .database.kite.kite_memory import UserMemory
from .util import i18n, llm, parent_watch
from .util.config import get_settings
from .routers import (assets, client_log, compose, compose_block, export, harness, import_sources, ingest, journey, kb, memory, note_harness, notes, profile,
                      settings as settings_router, skills, tree, writing_plan)

async def _settle_topics_once() -> None:
    if os.environ.get("MEMOKET_SKIP_TOPIC_SETTLE") == "1":
        return
    try:
        done = await asyncio.to_thread(UserMemory.settle_all_topics)
    except Exception as exc:      # noqa: BLE001
        print(f'[memory] Topic promotion backfill failed: {exc}')
        return
    for user, r in done.items():
        if "error" in r:
            print(f"[memory] {user} topic promotion backfill failed: {r['error']}")
        else:
            print(f"[memory] {user} filled {r['filled']} time buckets; promoted {len(r['promoted'])} topics")


async def _memory_janitor_loop() -> None:
    await _settle_topics_once()
    while True:
        await asyncio.sleep(60)
        try:
            n = UserMemory.evict_idle()
            if n:
                print(f'[memory] Evicted {n} idle indexes')
        except Exception as exc:      # noqa: BLE001
            print(f'[memory] Index cleanup failed: {exc}')


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    task = asyncio.create_task(_memory_janitor_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="memoket-NOTE", version="0.1.0", lifespan=_lifespan,
              description='AI note editor and knowledge base with long-term memory powered by KITE')


_orphans = store.sweep_orphan_jobs()
_stale_pauses = store.sweep_stale_snapshots()
_old_rows = store.sweep_old_rows()
_recited = store.reindex_citations()
if _recited:
    print(f'[startup] Rebuilt citations for {_recited} notes')
if any(_old_rows.values()):
    print(f'[startup] Pruned expired records: {_old_rows}')
if _stale_pauses:
    print(f'[startup] Removed {_stale_pauses} paused workflows older than {store.SNAPSHOT_MAX_AGE_DAYS} days')
_orphan_plans = store.sweep_orphan_plans()
_payloads = store.prune_job_payloads(pathlib.Path(get_settings().kite_data_dir) / "jobs")
_orphan_assets = store.sweep_orphan_assets(pathlib.Path(get_settings().kite_data_dir) / "assets")
if _orphan_assets["removed"]:
    print(f"[startup] Removed {_orphan_assets['removed']} unreferenced images ({_orphan_assets['bytes'] / 1024 / 1024:.1f}MB, older than 7 days)")
_vac = store.vacuum_if_bloated()
if _vac.get("vacuumed"):
    print(f"[startup] Note database VACUUM: {_vac['before_mb']}MB → {_vac['after_mb']}MB (free pages {_vac['free_mb']}MB)")
if _payloads:
    print(f'[startup] Removed {_payloads} completed import payloads')
if _orphan_plans:
    print(f'[startup] Invalidated {_orphan_plans} writing plans whose parent was deleted')
if _orphans:
    print(f'[startup] Removed {_orphans} interrupted import jobs')


try:
    _bk = backup.maybe_backup(store._db_path())
    if _bk:
        print(f'[startup] Note database backup: {_bk}')
    _kb = backup.maybe_backup_kb(store._db_path().parent)
    if _kb:
        print(f'[startup] Weekly knowledge backup: {len(_kb)} users')
except Exception as _exc:                                  # noqa: BLE001
    print(f'[startup] Database backup failed: {_exc}')


parent_watch.install_from_env()

_settings = get_settings()


_STARTED_AT = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@app.exception_handler(httpx.HTTPError)
async def _llm_unreachable(_request: Request, exc: httpx.HTTPError):
    return JSONResponse({"detail": llm.describe_error(exc)}, status_code=502)


@app.middleware("http")
async def _reject_cross_site_writes(request: Request, call_next):
    llm.ctx_user.set((request.headers.get("x-user-id") or "default").strip()[:64])
    i18n.ctx_lang.set(i18n.pick(request.headers.get("x-lang")))
    parts = [p for p in request.url.path.split("/") if p and p != "api"]
    llm.ctx_feature.set("/".join(p for p in parts if not (len(p) >= 12 and all(ch in "0123456789abcdef" for ch in p)))[:60])
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin", "")
        if request.headers.get("sec-fetch-site", "") == "cross-site" or \
                (origin and (urlparse(origin).hostname or "") not in _LOCAL_HOSTS):
            return JSONResponse({"detail": i18n.msg("This local API does not accept write requests from other sites")}, status_code=403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(journey.router)
app.include_router(client_log.router)
app.include_router(notes.router)
app.include_router(tree.router)
app.include_router(writing_plan.router)
app.include_router(note_harness.router)
app.include_router(skills.router)
app.include_router(ingest.router)
app.include_router(import_sources.router)
app.include_router(memory.router)
app.include_router(kb.router)
app.include_router(harness.router)
app.include_router(compose.router)
app.include_router(compose_block.router)
app.include_router(profile.router)
app.include_router(settings_router.router)
app.include_router(export.router)


@app.get("/api/health")
async def health():
    active = store.get_active_llm_config()

    async def llm_healthy() -> bool:
        if not store.llm_configured()["configured"]:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{active['base_url']}/models",
                                     headers={"Authorization": f"Bearer {active['api_key']}"})
                return r.status_code == 200
        except Exception:
            return False


    llm_ok, asr_ok = await asyncio.gather(llm_healthy(), asr.healthy())
    import resource
    rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024))

    try:
        import subprocess
        rss_now_mb = int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], timeout=2).strip()) // 1024
    except Exception:      # noqa: BLE001
        rss_now_mb = 0
    asr_cfg = asr.active_config()
    return {
        "status": "ok",


        "backend": {
            "pid": os.getpid(),
            "data_dir": str(get_settings().kite_data_dir),
            "started_at": _STARTED_AT,
        },

        "llm": {"ok": llm_ok, "base_url": active["base_url"], "model": active["model"], **store.llm_configured()},
        # Speech-to-text: active provider and the host it talks to (keys are never included).
        "asr": {"ok": asr_ok, "provider": asr_cfg["provider"],
                "base_url": asr_cfg["base_url"]},

        "memory": {"rss_peak_mb": rss_mb, "rss_mb": rss_now_mb, **UserMemory.cache_info()},
    }


def _web_dir() -> pathlib.Path | None:
    env = os.getenv("MEMOKET_NOTE_WEB_DIR")
    if env:
        p = pathlib.Path(env)
        return p if (p / "index.html").exists() else None
    p = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return p if (p / "index.html").exists() else None


@app.api_route("/api/{rest:path}",
               methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
               include_in_schema=False)
async def _api_not_found(rest: str):
    raise HTTPException(404, f'Endpoint not found: /api/{rest}')


class _NoStoreIndex(StaticFiles):
    async def get_response(self, path: str, scope):  # type: ignore[override]
        resp = await super().get_response(path, scope)
        if path in ("", ".", "index.html") or path.endswith("/index.html"):
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp


_web = _web_dir()
if _web:

    app.mount("/", _NoStoreIndex(directory=str(_web), html=True), name="web")
    print(f'[startup] Serving frontend: {_web}')
