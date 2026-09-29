"""Append-only log of operator console requests."""

from __future__ import annotations

from ..domain.requests import OUTCOMES, RequestRecord
from ..store.keys import KEY_REQUESTS
from ..store.snapshot import load_events, save_events

#: Number of request records kept in memory and on disk.
MAX_REQUESTS = 1000

#: Default number of records returned by a query without an explicit limit.
DEFAULT_REQUEST_LIMIT = 50


class RequestOps:
    """Stores a bounded, persistent trail of every operator request."""

    def record_request(self, record: RequestRecord) -> int:
        """Append a request record; returns the number of trimmed entries."""

        self.state.requests.append(record)
        dropped = 0
        if len(self.state.requests) > MAX_REQUESTS:
            dropped = len(self.state.requests) - MAX_REQUESTS
            del self.state.requests[:dropped]
        self._flush_requests()
        return dropped

    def requests(self) -> tuple[RequestRecord, ...]:
        return tuple(self.state.requests)

    def query_requests(
        self, outcome: str = "", limit: int = 0
    ) -> list[RequestRecord]:
        """Newest-first request records, optionally filtered by outcome."""

        cap = limit if limit > 0 else DEFAULT_REQUEST_LIMIT
        found: list[RequestRecord] = []
        for record in reversed(self.state.requests):
            if outcome and record.outcome != outcome:
                continue
            found.append(record)
            if len(found) >= cap:
                break
        return found

    def restore_requests(self) -> int:
        """Reload the request log from disk; returns the number restored."""

        raw = load_events(self.store, KEY_REQUESTS)
        restored = [RequestRecord.from_dict(item) for item in raw]
        self.state.requests = restored[-MAX_REQUESTS:]
        return len(self.state.requests)

    def flush_requests(self) -> int:
        payload = [record.to_dict() for record in self.state.requests]
        save_events(self.store, KEY_REQUESTS, payload)
        return self.store.rotate(KEY_REQUESTS, MAX_REQUESTS)

    def _flush_requests(self) -> int:
        return self.flush_requests()
