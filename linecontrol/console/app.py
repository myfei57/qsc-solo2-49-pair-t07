"""Flask application factory for the console."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from ..line.machine import Line
from ..domain.requests import RESULT_DENIED, RESULT_ERROR, RESULT_INPUT, RESULT_OK
from .api import Api, ApiParamError
from .errors import (
    CATEGORY_DENIED,
    CATEGORY_INPUT,
    describe_domain_error,
    describe_internal_error,
    describe_param_error,
)

LOGGER = logging.getLogger("linecontrol.console")

Handler = Callable[[object], dict[str, object]]

#: Content types served from the static web root.
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def _route_table(api: Api) -> tuple[tuple[str, str, str, Handler], ...]:
    """Pair each URL rule with its action key and bound handler."""

    return (
        ("/api/state", "GET", "", api.state),
        ("/api/report", "GET", "", api.report),
        ("/api/sequence", "GET", "", api.sequence),
        ("/api/sequence/clear", "POST", "sequence.clear", api.sequence_clear),
        ("/api/machines", "GET", "", api.machines),
        ("/api/bus", "GET", "", api.bus_view),
        ("/api/store", "GET", "", api.store_view),
        ("/api/events", "GET", "", api.events),
        ("/api/audit", "GET", "", api.audit),
        ("/api/audit/summary", "GET", "", api.audit_summary),
        ("/api/audit/requests", "GET", "", api.requests),
        ("/api/weld/confirm", "POST", "weld.confirm", api.weld_confirm),
        ("/api/weld/splice", "POST", "weld.splice", api.weld_splice),
        ("/api/weld/power", "POST", "weld.power", api.weld_power),
        ("/api/weld/seams", "GET", "", api.weld_seams),
        ("/api/weld/alarm", "POST", "weld.alarm", api.weld_alarm),
        ("/api/weld/clear", "POST", "weld.clear", api.weld_clear),
        ("/api/weld/release", "POST", "weld.release", api.weld_release),
        ("/api/tension/calibrate", "POST", "tension.calibrate", api.tension_calibrate),
        ("/api/tension/ramp", "POST", "tension.ramp", api.tension_ramp),
        ("/api/tension/persisted", "GET", "", api.tension_persisted),
        ("/api/pump/start", "POST", "pump.start", api.pump_start),
        ("/api/pump/resume", "POST", "pump.resume", api.pump_resume),
        ("/api/pump/replenish", "POST", "pump.replenish", api.pump_replenish),
        ("/api/pickle/calibrate", "POST", "pickle.calibrate", api.pickle_calibrate),
        ("/api/dry/heat", "POST", "dry.heat", api.dry_heat),
        ("/api/dry/dew", "POST", "dry.dew", api.dry_dew),
        ("/api/dry/heat-target", "POST", "dry.heat-target", api.dry_heat_target),
        ("/api/dry/reheat", "POST", "dry.reheat", api.dry_reheat),
        ("/api/exit/coil-change", "POST", "exit.coil-change", api.coil_change),
        ("/api/exit/taper", "POST", "exit.taper", api.exit_taper),
        ("/api/exit/weight", "POST", "exit.weight", api.exit_weight),
        ("/api/exit/shear-offset", "POST", "exit.shear-offset", api.shear_offset),
        ("/api/entry/offset", "POST", "entry.offset", api.entry_offset),
        ("/api/entry/correct", "POST", "entry.correct", api.entry_correct),
        ("/api/entry/sample", "POST", "entry.sample", api.entry_sample),
        ("/api/head/track", "POST", "head.track", api.head_track),
        ("/api/strip/advance", "POST", "strip.advance", api.strip_advance),
        ("/api/strip/speed", "POST", "strip.speed", api.strip_speed),
        ("/api/strip/sag", "GET", "", api.strip_sag),
        ("/api/strip/eta", "GET", "", api.strip_eta),
        ("/api/stop", "POST", "stop", api.stop),
        ("/api/cycle", "POST", "cycle", api.cycle),
    )


def _failure_body(view: object, message: str) -> dict[str, object]:
    info = view.to_dict()
    category = info["errorType"]
    body: dict[str, object] = {
        "ok": False,
        "error": message,
        "errorType": category,
        "title": info["title"],
        "hint": info["hint"],
        "code": info["code"],
    }
    if category in (CATEGORY_DENIED, CATEGORY_INPUT) and info["code"] != "bad-param":
        body["detail"] = {"code": info["code"], "detail": info["detail"]}
    elif info["detail"]:
        body["detailText"] = info["detail"]
    return body


def _bind(api: Api, action: str, handler: Handler) -> Callable[[], tuple[Response, int]]:
    """Run one handler, classify failures and leave an auditable request log."""

    def view() -> tuple[Response, int]:
        started = time.monotonic()
        handle = api.line.audit.new_handle()
        status = 200
        code = ""
        message = ""
        result = RESULT_OK
        payload: dict[str, object] = {}
        try:
            payload = handler(request)
            payload.setdefault("handle", handle)
        except ApiParamError as error:
            status = 400
            result = RESULT_INPUT
            code = "bad-param"
            message = str(error)
            payload = _failure_body(describe_param_error(error.name, error.raw), message)
            LOGGER.info("refused %s by %s: %s", action, Api.operator_of(request), message)
        except RuntimeError as error:
            status = 409
            view_info = describe_domain_error(error)
            result = (
                RESULT_INPUT if view_info.category == CATEGORY_INPUT else RESULT_DENIED
            )
            code = view_info.code
            message = str(error)
            payload = _failure_body(view_info, message)
            LOGGER.info("refused %s by %s: %s", action, Api.operator_of(request), message)
        except Exception as error:  # noqa: BLE001 - last-resort console guard
            status = 500
            result = RESULT_ERROR
            view_info = describe_internal_error(error)
            code = view_info.code
            message = str(error)
            payload = _failure_body(view_info, message)
            LOGGER.exception("handler %s failed", action)
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            if action:
                api.record_request(
                    action,
                    request,
                    result=result,
                    status=status,
                    duration_ms=duration_ms,
                    handle=handle,
                    code=code,
                    message=message,
                )
        return jsonify(payload), status

    view.__name__ = getattr(handler, "__name__", "handler")
    view.__doc__ = getattr(handler, "__doc__", None)
    return view


def create_app(line: Line, web_dir: str | Path) -> Flask:
    """Build the console application around an initialised line."""

    root = Path(web_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"web root is not a directory: {root}")

    api = Api(line)
    app = Flask(__name__, static_folder=None)
    app.config["LINE_API"] = api

    for rule, method, action, handler in _route_table(api):
        app.add_url_rule(
            rule,
            endpoint=f"{method}:{rule}",
            view_func=_bind(api, action, handler),
            methods=[method],
        )

    def index() -> Response:
        return send_from_directory(root, "index.html")

    def assets(filename: str) -> Response:
        suffix = Path(filename).suffix.lower()
        return send_from_directory(root, filename, mimetype=STATIC_TYPES.get(suffix))

    app.add_url_rule("/", endpoint="index", view_func=index)
    app.add_url_rule("/<path:filename>", endpoint="assets", view_func=assets)
    return app
