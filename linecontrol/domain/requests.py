"""Operator request audit record.

Every mutating console request leaves one :class:`RequestRecord` behind,
whether it succeeded or was refused, so the log can answer afterwards
who asked for what, when, and what the line said back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .events import utcnow
from .records import _stamp

#: Outcome classes shared by the backend and the browser console.
RESULT_OK = "ok"
RESULT_INPUT = "input"
RESULT_DENIED = "denied"
RESULT_ERROR = "error"


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """One operator request and how the line answered it."""

    action: str
    label: str
    method: str
    path: str
    operator: str
    ok: bool
    result: str = RESULT_OK
    status: int = 200
    code: str = ""
    message: str = ""
    params: dict[str, str] = field(default_factory=dict)
    duration_ms: int = 0
    handle: str = ""
    at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "label": self.label,
            "method": self.method,
            "path": self.path,
            "operator": self.operator,
            "ok": self.ok,
            "result": self.result,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "params": dict(self.params),
            "durationMs": self.duration_ms,
            "handle": self.handle,
            "at": self.at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RequestRecord":
        params = raw.get("params", {})
        return cls(
            action=str(raw.get("action", "")),
            label=str(raw.get("label", "")),
            method=str(raw.get("method", "")),
            path=str(raw.get("path", "")),
            operator=str(raw.get("operator", "")),
            ok=bool(raw.get("ok", False)),
            result=str(raw.get("result", RESULT_ERROR)),
            status=int(raw.get("status", 0)),
            code=str(raw.get("code", "")),
            message=str(raw.get("message", "")),
            params={str(k): str(v) for k, v in params.items()}
            if isinstance(params, dict)
            else {},
            duration_ms=int(raw.get("durationMs", 0)),
            handle=str(raw.get("handle", "")),
            at=_stamp(raw.get("at")),
        )
