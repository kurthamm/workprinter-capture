"""The web page's API. Thin: every handler reads or pokes the Service and returns."""

from __future__ import annotations

import asyncio
import itertools
import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from wpcap.config import AppConfig, verify_password
from wpcap.machine import Machine, ReelMeta
from wpcap.pictures import to_jpeg
from wpcap.runner import SimRunner
from wpcap.service import Service
from wpcap.web.auth import COOKIE, SESSION_DAYS, check_token, make_token

STATIC = Path(__file__).parent / "static"
STATUS_PERIOD_S = 0.5
WRONG_PASSWORD_DELAY_S = 1.0
# Password checks running at once. scrypt takes about 50 ms of CPU and a thread from the pool
# the event streams also use; parallel login attempts queue here instead of saturating both.
LOGIN_CHECKS_AT_ONCE = 2


class LoginBody(BaseModel):
    password: str


class DelayBody(BaseModel):
    delay_ms: float


class NewReelBody(BaseModel):
    name: str | None = None
    film_type: str = "super8"
    notes: str = ""
    customer: str = ""
    job_number: str = ""

CALIBRATION_SETS_KEPT = 4


def create_app(service: Service, config: AppConfig) -> FastAPI:
    app = FastAPI(title="WorkPrinter Capture", docs_url=None, redoc_url=None, openapi_url=None)
    # Set by the server on shutdown so open event streams end instead of blocking it.
    app.state.shutting_down = threading.Event()
    secret = config.server.secret
    # Each calibration request keeps its own pictures under its own id, so a page still loading
    # an earlier strip never shows pictures of a later one beside the earlier offsets.
    calibration_sets: dict[str, dict[int, list[bytes]]] = {}
    calibration_ids = itertools.count(1)
    cal_lock = threading.Lock()
    # Per app, not per module: an asyncio.Semaphore binds to the event loop that first waits
    # on it, and each server run (and each test client) has its own loop.
    login_checks = asyncio.Semaphore(LOGIN_CHECKS_AT_ONCE)

    # ---- auth ------------------------------------------------------------------------------

    def require_login(request: Request) -> None:
        token = request.cookies.get(COOKIE)
        if token is None or not check_token(secret, token, SESSION_DAYS * 86400):
            raise HTTPException(401, "login required")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {
                "error": str(exc.errors()[0]["msg"])
                + ": "
                + ".".join(str(x) for x in exc.errors()[0]["loc"])
            },
            status_code=400,
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/api/login")
    async def login(body: LoginBody, response: Response):
        async with login_checks:
            stored = config.server.password_hash
            ok = await asyncio.to_thread(verify_password, body.password, stored)
        if not ok:
            await asyncio.sleep(WRONG_PASSWORD_DELAY_S)
            raise HTTPException(401, "wrong password")
        response.set_cookie(
            COOKIE,
            make_token(secret, time.time()),
            max_age=SESSION_DAYS * 86400,
            httponly=True,
            secure=True,
            samesite="strict",
        )
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    # ---- status and events -----------------------------------------------------------------

    def machine(name: str) -> Machine:
        try:
            return service.machine(name)
        except KeyError:
            raise HTTPException(404, f"no machine named {name!r}") from None

    @app.get("/api/status", dependencies=[Depends(require_login)])
    def status():
        return service.snapshot()

    @app.get("/api/alerts", dependencies=[Depends(require_login)])
    def alerts():
        return {"alerts": [a.as_dict() for a in service.bus.recent(50)]}

    @app.get("/api/events", dependencies=[Depends(require_login)])
    async def events(request: Request):
        async def gen():
            sub = service.bus.subscribe()
            try:
                hello = {"alerts": [a.as_dict() for a in service.bus.recent(50)]}
                yield f"event: hello\ndata: {json.dumps(hello)}\n\n"
                next_status = 0.0
                while not app.state.shutting_down.is_set() and not await request.is_disconnected():
                    now = time.monotonic()
                    if now >= next_status:
                        next_status = now + STATUS_PERIOD_S
                        snap = await asyncio.to_thread(service.snapshot)
                        yield f"event: status\ndata: {json.dumps(snap)}\n\n"
                    alert = await asyncio.to_thread(sub.get, 0.1)
                    while alert is not None:
                        yield f"event: alert\ndata: {json.dumps(alert.as_dict())}\n\n"
                        alert = sub.get(0)
            finally:
                sub.close()

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # ---- pictures --------------------------------------------------------------------------

    def jpeg(data: bytes, **headers: str) -> Response:
        return Response(
            data, media_type="image/jpeg", headers={"Cache-Control": "no-store", **headers}
        )

    @app.get("/api/machines/{name}/live.jpg", dependencies=[Depends(require_login)])
    def live(name: str):
        p = machine(name).live_picture()
        if p is None:
            raise HTTPException(404, "no picture from the camera yet")
        return jpeg(to_jpeg(p.pixels))

    @app.get("/api/machines/{name}/last.jpg", dependencies=[Depends(require_login)])
    def last(name: str):
        got = machine(name).last_saved()
        if got is None:
            raise HTTPException(404, "no frame saved yet")
        n, p = got
        return jpeg(to_jpeg(p.pixels), **{"X-Frame-Number": str(n)})

    @app.get("/api/machines/{name}/calibration", dependencies=[Depends(require_login)])
    def calibration(name: str):
        m = machine(name)
        window = m.click_window()
        pics = [to_jpeg(p.pixels) for _, p in window]
        with cal_lock:
            sets = calibration_sets.setdefault(name, {})
            set_id = next(calibration_ids)
            sets[set_id] = pics
            while len(sets) > CALIBRATION_SETS_KEPT:
                del sets[min(sets)]
        return {
            "delay_ms": m.config.delay_ms,
            "pictures": [
                {
                    "offset_ms": off,
                    "url": f"/api/machines/{quote(name, safe='')}/calibration/{set_id}/{i}.jpg",
                }
                for i, (off, _) in enumerate(window)
            ],
        }

    @app.get(
        "/api/machines/{name}/calibration/{set_id}/{i}.jpg",
        dependencies=[Depends(require_login)],
    )
    def calibration_picture(name: str, set_id: int, i: int):
        machine(name)
        with cal_lock:
            pics = calibration_sets.get(name, {}).get(set_id, [])
            if not 0 <= i < len(pics):
                raise HTTPException(404, "calibration picture gone; fetch calibration again")
            return jpeg(pics[i])

    # ---- actions ---------------------------------------------------------------------------

    def act(fn):
        try:
            return fn()
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/machines/{name}/delay", dependencies=[Depends(require_login)])
    def set_delay(name: str, body: DelayBody):
        m = machine(name)
        act(lambda: m.set_delay_ms(body.delay_ms))
        return {"ok": True, "delay_ms": m.config.delay_ms}

    @app.post("/api/machines/{name}/new-reel", dependencies=[Depends(require_login)])
    def new_reel(name: str, body: NewReelBody):
        m = machine(name)
        runner = service.runner(name)
        meta = ReelMeta(
            name=body.name or None,
            film_type=body.film_type,
            notes=body.notes,
            customer=body.customer,
            job_number=body.job_number,
        )

        def go():
            if isinstance(runner, SimRunner):
                runner.new_reel(meta)  # also threads the fresh simulated film
            else:
                m.new_reel(meta)

        act(go)
        return {"ok": True, "reel": body.name or None}

    @app.post("/api/machines/{name}/stop", dependencies=[Depends(require_login)])
    def stop(name: str):
        act(machine(name).stop)
        return {"ok": True}

    @app.post("/api/machines/{name}/resume", dependencies=[Depends(require_login)])
    def resume(name: str):
        act(machine(name).resume)
        return {"ok": True}

    # ---- page ------------------------------------------------------------------------------

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
