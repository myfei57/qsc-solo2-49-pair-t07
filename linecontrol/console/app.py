"""Flask application factory for the console."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from flask import Flask, Response, jsonify, request, send_from_directory

from ..domain.requests import (
    OUTCOME_FAILURE,
    OUTCOME_INPUT,
    OUTCOME_OK,
    OUTCOME_REJECTED,
    OUTCOMES,
    RequestRecord,
)
from ..line.machine import Line
from .api import Api, ApiParamError

Handler = Callable[[object], dict[str, object]]

LOGGER = logging.getLogger("linecontrol.console")

#: Content types served from the static web root.
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}

#: Header carrying the logged-in operator's display name.
OPERATOR_HEADER = "X-Operator"

#: Set by the browser on unattended polling calls so they do not fill the trail.
AUTO_HEADER = "X-Auto-Request"

#: Outcome tag -> HTTP status used for every error reply.
ERROR_STATUS = {
    OUTCOME_INPUT: 400,
    OUTCOME_REJECTED: 409,
    OUTCOME_FAILURE: 500,
}

#: Outcome tag -> message shown when the exception carries none of its own.
GENERIC_MESSAGE = {
    OUTCOME_INPUT: "请求参数有误，请检查输入",
    OUTCOME_REJECTED: "当前设备状态不允许此操作",
    OUTCOME_FAILURE: "服务器内部错误，请联系维护人员",
}

#: Domain error codes -> wording an operator on the floor understands.
CODE_MESSAGE = {
    "level-low": "槽体液位低于最低允许值，请先补液",
    "strip-run": "带钢正在运行，不能执行该操作",
    "no-replenish": "当前工况不允许补酸",
    "no-coil": "没有载入钢卷，请先上卷",
    "interlock-held": "焊接联锁未释放，不能执行该操作",
    "alarm-active": "存在活动告警，请先复位告警",
    "rinse-active": "喷淋正在进行，不能执行该操作",
    "track-stale": "焊缝跟踪数据过期，请先刷新跟踪",
    "tank-volume": "槽体容积必须为正数",
    "offset-invalid": "偏移值超出允许范围",
    "no-exhaust": "排风未建立，不能升温",
    "dew-high": "露点温度过高，不能继续升温",
    "temp-range": "温度超出允许范围",
    "tail-unflushed": "带尾残酸未冲净，不能停机/换卷",
    "no-speed": "速度设定无效",
    "invalid-gain": "增益必须为正数",
    "invalid-speed": "目标速度必须为正数",
    "not-persisted": "张力数据未落盘，不能执行该操作",
    "ramp-unready": "张力尚未稳定，不能提速",
    "align-pending": "对中尚未确认，不能焊接",
    "arc-blocked": "焊接电弧门关闭，禁止起弧",
    "latch-held": "联锁锁扣保持中，不能执行该操作",
    "power-invalid": "焊接电压/电流超出允许范围",
}


def _route_table(api: Api) -> tuple[tuple[str, str, Handler], ...]:
    """Pair each URL rule with the bound handler that serves it."""

    return (
        ("/api/state", "GET", api.state),
        ("/api/report", "GET", api.report),
        ("/api/sequence", "GET", api.sequence),
        ("/api/sequence/clear", "POST", api.sequence_clear),
        ("/api/machines", "GET", api.machines),
        ("/api/bus", "GET", api.bus_view),
        ("/api/store", "GET", api.store_view),
        ("/api/events", "GET", api.events),
        ("/api/audit", "GET", api.audit),
        ("/api/audit/summary", "GET", api.audit_summary),
        ("/api/requests", "GET", api.requests),
        ("/api/weld/confirm", "POST", api.weld_confirm),
        ("/api/weld/splice", "POST", api.weld_splice),
        ("/api/weld/power", "POST", api.weld_power),
        ("/api/weld/seams", "GET", api.weld_seams),
        ("/api/weld/alarm", "POST", api.weld_alarm),
        ("/api/weld/clear", "POST", api.weld_clear),
        ("/api/weld/release", "POST", api.weld_release),
        ("/api/tension/calibrate", "POST", api.tension_calibrate),
        ("/api/tension/ramp", "POST", api.tension_ramp),
        ("/api/tension/persisted", "GET", api.tension_persisted),
        ("/api/pump/start", "POST", api.pump_start),
        ("/api/pump/resume", "POST", api.pump_resume),
        ("/api/pump/replenish", "POST", api.pump_replenish),
        ("/api/pickle/calibrate", "POST", api.pickle_calibrate),
        ("/api/dry/heat", "POST", api.dry_heat),
        ("/api/dry/dew", "POST", api.dry_dew),
        ("/api/dry/heat-target", "POST", api.dry_heat_target),
        ("/api/dry/reheat", "POST", api.dry_reheat),
        ("/api/exit/coil-change", "POST", api.coil_change),
        ("/api/exit/taper", "POST", api.exit_taper),
        ("/api/exit/weight", "POST", api.exit_weight),
        ("/api/exit/shear-offset", "POST", api.shear_offset),
        ("/api/entry/offset", "POST", api.entry_offset),
        ("/api/entry/correct", "POST", api.entry_correct),
        ("/api/entry/sample", "POST", api.entry_sample),
        ("/api/head/track", "POST", api.head_track),
        ("/api/strip/advance", "POST", api.strip_advance),
        ("/api/strip/speed", "POST", api.strip_speed),
        ("/api/strip/sag", "GET", api.strip_sag),
        ("/api/strip/eta", "GET", api.strip_eta),
        ("/api/stop", "POST", api.stop),
        ("/api/cycle", "POST", api.cycle),
    )


def _operator() -> str:
    raw = (request.headers.get(OPERATOR_HEADER, "") or "").strip()
    return raw[:32] if raw else "anonymous"


def _error_payload(outcome: str, error: Exception, ref: str) -> dict[str, object]:
    """Build the categorised error body shared with the browser."""

    code = getattr(error, "code", None)
    code_value = code.value if code is not None else ""
    fallback = GENERIC_MESSAGE[outcome]
    message = (
        CODE_MESSAGE.get(code_value)
        or getattr(error, "detail", "")
        or str(error)
        or fallback
    )
    payload: dict[str, object] = {
        "ok": False,
        "type": outcome,
        "code": code_value,
        "error": message,
        "ref": ref,
    }
    describe = getattr(error, "to_dict", None)
    if callable(describe):
        detail = describe()
        payload["detail"] = detail
        technical = detail.get("detail") if isinstance(detail, dict) else ""
        if technical and technical != message:
            payload["technical"] = technical
    return payload


def _bind(api: Api, handler: Handler) -> Callable[[], tuple[Response, int]]:
    """Wrap a handler: categorise errors and append a request audit record."""

    def view() -> tuple[Response, int] | Response:
        ref = uuid4().hex[:8]
        outcome = OUTCOME_OK
        status = 200
        body: dict[str, object] = {}
        try:
            body = handler(request)
            body.setdefault("ref", ref)
        except ApiParamError as error:
            outcome = OUTCOME_INPUT
            status = ERROR_STATUS[outcome]
            body = _error_payload(outcome, error, ref)
            body["error"] = f"参数 {error.name} 填写有误，请检查（原值：{error.raw or '空'}）"
        except ValueError as error:
            # e.g. an invalid enum query value slipped past the param parser
            outcome = OUTCOME_INPUT
            status = ERROR_STATUS[outcome]
            body = _error_payload(outcome, error, ref)
        except RuntimeError as error:
            outcome = OUTCOME_REJECTED
            status = ERROR_STATUS[outcome]
            body = _error_payload(outcome, error, ref)
        except Exception as error:  # noqa: BLE001 - last-resort envelope for the UI
            outcome = OUTCOME_FAILURE
            status = ERROR_STATUS[outcome]
            LOGGER.exception("request %s %s failed", request.method, request.path)
            body = _error_payload(outcome, error, ref)
        _record(api, outcome, status, body)
        return jsonify(body), status

    view.__name__ = getattr(handler, "__name__", "handler")
    view.__doc__ = getattr(handler, "__doc__", None)
    return view


def _record(
    api: Api, outcome: str, status: int, body: dict[str, object]
) -> None:
    """Persist one operator request; polling successes are dropped to avoid noise."""

    automatic = request.headers.get(AUTO_HEADER, "").strip() == "1"
    if automatic and outcome == OUTCOME_OK:
        return
    record = RequestRecord(
        method=request.method,
        path=request.path,
        operator=_operator(),
        status=status,
        outcome=outcome,
        message=str(body.get("error", "")) if outcome != OUTCOME_OK else "",
        code=str(body.get("code", "")) if outcome != OUTCOME_OK else "",
        remote=request.remote_addr or "",
        ref=str(body.get("ref", "")),
        params={key: request.args.get(key, "") for key in request.args},
    )
    try:
        api.line.audit.record_request(record)
    except Exception:  # noqa: BLE001 - logging must never break the response
        LOGGER.exception("could not persist request record for %s", request.path)


def create_app(line: Line, web_dir: str | Path) -> Flask:
    """Build the console application around an initialised line."""

    root = Path(web_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"web root is not a directory: {root}")

    api = Api(line)
    app = Flask(__name__, static_folder=None)
    app.config["LINE_API"] = api

    for rule, method, handler in _route_table(api):
        app.add_url_rule(
            rule,
            endpoint=handler.__name__,
            view_func=_bind(api, handler),
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
