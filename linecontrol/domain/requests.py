"""Operator request record kept by the console audit trail."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .events import utcnow

#: The request satisfied every validation and the domain accepted it.
OUTCOME_OK = "ok"

#: The operator supplied missing or malformed parameters (HTTP 400).
OUTCOME_INPUT = "input"

#: Parameters were valid but the equipment state forbade the action (HTTP 409).
OUTCOME_REJECTED = "rejected"

#: The server hit an unexpected failure while handling the request (HTTP 500).
OUTCOME_FAILURE = "failure"

OUTCOMES: tuple[str, ...] = (
    OUTCOME_OK,
    OUTCOME_INPUT,
    OUTCOME_REJECTED,
    OUTCOME_FAILURE,
)


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """One console request, logged regardless of whether it succeeded."""

    method: str
    path: str
    operator: str
    status: int
    outcome: str
    at: datetime = field(default_factory=utcnow)
    message: str = ""
    code: str = ""
    remote: str = ""
    ref: str = ""
    params: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "method": self.method,
            "path": self.path,
            "operator": self.operator,
            "remote": self.remote,
            "status": self.status,
            "outcome": self.outcome,
            "code": self.code,
            "message": self.message,
            "ref": self.ref,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RequestRecord":
        at = raw.get("at")
        if isinstance(at, str):
            stamp = datetime.fromisoformat(at)
        elif isinstance(at, datetime):
            stamp = at
        else:
            stamp = utcnow()
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        raw_params = raw.get("params", {})
        params = (
            {str(key): str(value) for key, value in raw_params.items()}
            if isinstance(raw_params, dict)
            else {}
        )
        return cls(
            method=str(raw.get("method", "")),
            path=str(raw.get("path", "")),
            operator=str(raw.get("operator", "")),
            status=int(raw.get("status", 0)),
            outcome=str(raw.get("outcome", OUTCOME_FAILURE)),
            at=stamp,
            message=str(raw.get("message", "")),
            code=str(raw.get("code", "")),
            remote=str(raw.get("remote", "")),
            ref=str(raw.get("ref", "")),
            params=params,
        )
