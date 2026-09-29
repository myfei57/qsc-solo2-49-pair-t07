"""HTTP console endpoints."""

from __future__ import annotations

from pathlib import Path

from flask.testing import FlaskClient

from linecontrol.console.app import create_app
from linecontrol.line.machine import Line

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


def test_state_and_static(client: FlaskClient) -> None:
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.get_json()["state"]["phase"] == "idle"
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/missing.txt").status_code == 404


def test_read_only_endpoints(client: FlaskClient) -> None:
    for path in (
        "/api/report",
        "/api/machines",
        "/api/bus",
        "/api/store",
        "/api/events",
        "/api/audit",
        "/api/audit/summary",
        "/api/weld/seams",
        "/api/tension/persisted",
        "/api/strip/sag",
        "/api/sequence",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.get_json()["ok"] is True


def test_missing_parameter_is_a_bad_request(client: FlaskClient) -> None:
    response = client.post("/api/entry/sample")
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["type"] == "input"
    assert body["code"] == ""
    assert body["ref"]


def test_domain_failure_is_a_conflict(client: FlaskClient) -> None:
    response = client.post("/api/entry/sample?value=abc")
    assert response.status_code == 400
    response = client.post("/api/pump/start?level=1.0")
    assert response.status_code == 409
    body = response.get_json()
    assert body["ok"] is False
    assert body["type"] == "rejected"
    assert body["code"] == "level-low"
    assert body["detail"]["code"] == "level-low"
    assert body["error"]
    assert body["ref"]


def test_invalid_query_enum_is_an_input_error(client: FlaskClient) -> None:
    response = client.get("/api/audit?kind=not-a-kind")
    assert response.status_code == 400
    assert response.get_json()["type"] == "input"
    response = client.get("/api/requests?outcome=bogus")
    assert response.status_code == 400
    assert response.get_json()["type"] == "input"


def test_cycle_endpoint_runs_the_line(client: FlaskClient) -> None:
    response = client.post(
        "/api/cycle",
        query_string={
            "coil": "C-77",
            "target": 90,
            "level": 4.5,
            "voltage": 24,
            "current": 300,
            "speed": 1.4,
        },
    )
    assert response.status_code == 200
    sequence = response.get_json()["sequence"]
    assert sequence["label"] == "production"
    assert all(step["ok"] for step in sequence["steps"])
    state = client.get("/api/state").get_json()["state"]
    assert state["phase"] == "idle"
    assert state["weld"]["seam"]


def test_cycle_without_a_coil_is_rejected(client: FlaskClient) -> None:
    response = client.post("/api/cycle", query_string={"target": 90})
    assert response.status_code == 400


def test_weld_alarm_flow(client: FlaskClient) -> None:
    assert client.post("/api/weld/confirm").status_code == 409
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    client.post("/api/entry/sample?value=12")
    alarm = client.post("/api/weld/alarm").get_json()
    assert alarm["alarms"] == ["weld-overcurrent"]
    assert client.post("/api/weld/release").status_code == 409
    cleared = client.post("/api/weld/clear").get_json()
    assert cleared["cleared"] is True
    assert client.post("/api/weld/release").status_code == 200


def test_events_stream_records_bus_traffic(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=5")
    events = client.get("/api/events").get_json()["events"]
    assert isinstance(events, list)
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    events = client.get("/api/events").get_json()["events"]
    kinds = {event["kind"] for event in events}
    assert {"arc", "weld", "tension", "pump", "stop"} <= kinds


def test_audit_query_filters_by_kind(client: FlaskClient) -> None:
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    response = client.get("/api/audit?kind=arc&limit=5")
    events = response.get_json()["events"]
    assert events and all(event["kind"] == "arc" for event in events)
    summary = client.get("/api/audit/summary").get_json()["summary"]
    assert summary["arc"] >= 1


def test_store_view_lists_keys(client: FlaskClient) -> None:
    client.post("/api/cycle?coil=C-1&target=90&level=4.5&voltage=24&current=300&speed=1.4")
    view = client.get("/api/store").get_json()
    assert "weld.record" in view["keys"]
    assert "TensionSnapshot" in view["recordTypes"]


def test_machines_view(client: FlaskClient) -> None:
    machines = client.get("/api/machines").get_json()["machines"]
    assert set(machines) == {"weld", "pump", "dryer", "tension"}
    assert machines["weld"]["state"] == "idle"


def test_bus_view_reports_subscribers(client: FlaskClient) -> None:
    view = client.get("/api/bus").get_json()
    assert view["subscribers"]["arc"] >= 1


def test_taper_weight_and_eta(client: FlaskClient) -> None:
    taper = client.post("/api/exit/taper?base=40&diameter=120").get_json()
    assert taper["taper"] > 40.0
    weight = client.post(
        "/api/exit/weight?entry=2.5&exit=2.3&width=1250&length=4200"
    ).get_json()
    assert weight["weight"] > 0.0
    client.post("/api/strip/advance?delta=20")
    client.post("/api/strip/speed?speed=2")
    eta = client.get("/api/strip/eta?target=120").get_json()
    assert eta["eta"] > 0.0


def test_sequence_clear_endpoint(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=1")
    assert client.post("/api/sequence/clear").status_code == 200
    assert client.get("/api/sequence").get_json()["sequence"]["steps"] == []


def test_request_log_records_operator_action_and_filter(client: FlaskClient) -> None:
    client.post(
        "/api/pump/start?level=1.0",
        headers={"X-Operator": "王师傅"},
    )
    records = client.get("/api/requests?limit=50").get_json()["requests"]
    assert records, "a rejected operator action must still be logged"
    latest = records[0]
    assert latest["outcome"] == "rejected"
    assert latest["status"] == 409
    assert latest["operator"] == "王师傅"
    assert latest["method"] == "POST"
    assert latest["path"] == "/api/pump/start"
    assert latest["params"]["level"] == "1.0"
    assert latest["code"] == "level-low"
    assert latest["message"]
    assert latest["ref"]
    assert latest["at"]

    rejected = client.get("/api/requests?outcome=rejected").get_json()["requests"]
    assert rejected and all(row["outcome"] == "rejected" for row in rejected)

    # A successful action is logged too.
    client.post("/api/entry/sample?value=12", headers={"X-Operator": "王师傅"})
    latest = client.get("/api/requests?outcome=ok").get_json()["requests"][0]
    assert latest["path"] == "/api/entry/sample"
    assert latest["operator"] == "王师傅"


def test_request_log_skips_successful_background_polls(client: FlaskClient) -> None:
    for _ in range(3):
        client.get("/api/state", headers={"X-Auto-Request": "1"})
    records = client.get(
        "/api/requests", headers={"X-Auto-Request": "1"}
    ).get_json()["requests"]
    assert records == []

    # A failed background call is still worth keeping.
    client.post(
        "/api/pump/start?level=1.0",
        headers={"X-Auto-Request": "1"},
    )
    records = client.get(
        "/api/requests?outcome=rejected",
        headers={"X-Auto-Request": "1"},
    ).get_json()["requests"]
    assert len(records) == 1
    assert records[0]["path"] == "/api/pump/start"


def test_request_log_defaults_operator_to_anonymous(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=12")
    latest = client.get("/api/requests?outcome=ok").get_json()["requests"][0]
    assert latest["operator"] == "anonymous"


def test_request_log_survives_restart(tmp_path: Path) -> None:
    app = create_app(Line(tmp_path), WEB_ROOT)
    client = app.test_client()
    client.post(
        "/api/pump/start?level=1.0",
        headers={"X-Operator": "李班长"},
    )
    app.config["LINE_API"].close()

    restarted = create_app(Line(tmp_path), WEB_ROOT)
    restarted.config["LINE_API"].line.recover()
    reborn = restarted.test_client()
    records = reborn.get("/api/requests?outcome=rejected").get_json()["requests"]
    assert len(records) == 1
    assert records[0]["operator"] == "李班长"
    assert records[0]["code"] == "level-low"
    restarted.config["LINE_API"].close()

