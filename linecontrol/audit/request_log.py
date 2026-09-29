"""Append-only operator request log with a bounded on-disk window."""

from __future__ import annotations

from ..domain.requests import RequestRecord
from ..store.keys import KEY_REQUESTS
from ..store.snapshot import load_requests, save_requests
from .state import MAX_REQUESTS


class RequestLogOps:
    """Mixed into :class:`~linecontrol.audit.logger.Logger`."""

    def record_request(self, record: RequestRecord) -> int:
        """Append a request record; returns the number of trimmed entries."""

        self.state.requests.append(record)
        dropped = self.state.trim_requests(MAX_REQUESTS)
        self._flush_requests()
        return dropped

    def requests(self) -> tuple[RequestRecord, ...]:
        return tuple(self.state.requests)

    def recent_requests(self, limit: int = 0, failed_only: bool = False) -> list[RequestRecord]:
        """Newest-first request records, optionally limited to refusals."""

        found: list[RequestRecord] = []
        for record in reversed(self.state.requests):
            if failed_only and record.ok:
                continue
            found.append(record)
            if limit > 0 and len(found) >= limit:
                break
        return found

    def restore_requests(self) -> int:
        """Reload the request log from disk; returns the count restored."""

        raw = load_requests(self.store, KEY_REQUESTS)
        restored = [RequestRecord.from_dict(item) for item in raw]
        self.state.requests = restored
        self.state.trim_requests(MAX_REQUESTS)
        return len(self.state.requests)

    def flush_requests(self) -> int:
        return self._flush_requests()

    def _flush_requests(self) -> int:
        payload = [record.to_dict() for record in self.state.requests]
        save_requests(self.store, KEY_REQUESTS, payload)
        return self.store.rotate(KEY_REQUESTS, MAX_REQUESTS)
