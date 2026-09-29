"""Audit logger state."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.events import Event
from ..domain.requests import RequestRecord

#: Number of process events kept in memory and on disk.
MAX_EVENTS = 500

#: Number of operator request records kept in memory and on disk.
MAX_REQUESTS = 2000

#: Default number of events returned by a query without an explicit limit.
DEFAULT_QUERY_LIMIT = 50


@dataclass(slots=True)
class AuditState:
    events: list[Event] = field(default_factory=list)
    requests: list[RequestRecord] = field(default_factory=list)
    alarms: dict[str, bool] = field(default_factory=dict)

    def trim(self, keep: int = MAX_EVENTS) -> int:
        """Drop the oldest events beyond ``keep`` and report how many went."""

        if len(self.events) <= keep:
            return 0
        dropped = len(self.events) - keep
        del self.events[:dropped]
        return dropped

    def trim_requests(self, keep: int = MAX_REQUESTS) -> int:
        """Drop the oldest request records beyond ``keep``."""

        if len(self.requests) <= keep:
            return 0
        dropped = len(self.requests) - keep
        del self.requests[:dropped]
        return dropped
