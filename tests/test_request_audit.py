"""Classified error replies and the operator request audit trail."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_missing_parameter_is_classified_as_input(client: FlaskClient) -> None:
    response = client.post("/api/entry/sample")
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["errorType"] == "input"
    assert body["title"] == "参数填错"
    assert body["code"] == "bad-param"
    assert "value" in body["hint"]


def test_malformed_number_is_classified_as_input(client: FlaskClient) -> None:
    response = client.post("/api/strip/speed?speed=abc")
    body = response.get_json()
    assert response.status_code == 400
    assert body["errorType"] == "input"


def test_out_of_range_value_is_classified_as_input(client: FlaskClient) -> None:
    response = client.post("/api/tension/calibrate?gain=-1")
    body = response.get_json()
    # Domain value errors keep the 409 status but carry the input category.
    assert response.status_code == 409
    assert body["errorType"] == "input"
    assert body["detail"]["code"] == "invalid-gain"
    assert "张力增益" in body["hint"]


def test_interlock_refusal_is_classified_as_denied(client: FlaskClient) -> None:
    response = client.post("/api/pump/start?level=1.0")
    body = response.get_json()
    assert response.status_code == 409
    assert body["errorType"] == "denied"
    assert body["title"] == "设备不允许"
    assert body["detail"]["code"] == "level-low"
    assert "液位" in body["hint"]


def test_successful_request_is_logged(client: FlaskClient) -> None:
    response = client.post(
        "/api/entry/sample?value=5",
        headers={"X-Operator": "王芳"},
    )
    assert response.status_code == 200
    assert response.get_json()["handle"]

    records = client.get("/api/audit/requests?limit=10").get_json()["requests"]
    mine = [r for r in records if r["operator"] == "王芳"]
    assert len(mine) == 1
    rec = mine[0]
    assert rec["ok"] is True
    assert rec["result"] == "ok"
    assert rec["label"] == "位置采样"
    assert rec["action"] == "entry.sample"
    assert rec["path"] == "/api/entry/sample"
    assert rec["params"] == {"value": "5"}
    assert rec["handle"]
    assert rec["durationMs"] >= 0


def test_refused_request_is_logged_with_reason(client: FlaskClient) -> None:
    client.post("/api/pump/start?level=1.0", headers={"X-Operator": "李强"})
    client.post("/api/tension/calibrate?gain=-1", headers={"X-Operator": "李强"})

    records = client.get("/api/audit/requests?failed=1").get_json()["requests"]
    by_code = {r["code"]: r for r in records}
    assert set(by_code) >= {"level-low", "invalid-gain"}
    assert by_code["level-low"]["result"] == "denied"
    assert by_code["invalid-gain"]["result"] == "input"
    assert all(not r["ok"] for r in records)


def test_request_log_records_who_when_and_what(client: FlaskClient) -> None:
    client.post("/api/stop", headers={"X-Operator": "赵磊"})
    records = client.get("/api/audit/requests").get_json()["requests"]
    stops = [r for r in records if r["action"] == "stop"]
    assert len(stops) == 1
    rec = stops[0]
    assert rec["operator"] == "赵磊"
    assert rec["label"] == "停机"
    assert rec["at"]


def test_polling_gets_are_not_audited_as_requests(client: FlaskClient) -> None:
    for _ in range(3):
        client.get("/api/state")
        client.get("/api/audit")
        client.get("/api/events")
    records = client.get("/api/audit/requests").get_json()["requests"]
    assert records == []


def test_request_log_survives_restart(tmp_path, client: FlaskClient) -> None:
    client.post("/api/stop", headers={"X-Operator": "钱七"})

    from pathlib import Path

    from linecontrol.console.app import create_app
    from linecontrol.line.machine import Line

    root = Path(__file__).resolve().parents[1] / "web"
    line2 = Line(tmp_path)
    line2.recover()
    client2 = create_app(line2, root).test_client()
    records = client2.get("/api/audit/requests").get_json()["requests"]
    assert any(r["operator"] == "钱七" and r["action"] == "stop" for r in records)


def test_unknown_audit_kind_is_a_param_error(client: FlaskClient) -> None:
    response = client.get("/api/audit?kind=bogus")
    assert response.status_code == 400
    assert response.get_json()["errorType"] == "input"


def test_request_filter_returns_newest_first(client: FlaskClient) -> None:
    client.post("/api/entry/sample?value=1", headers={"X-Operator": "A"})
    client.post("/api/entry/sample?value=2", headers={"X-Operator": "B"})
    records = client.get("/api/audit/requests?limit=10").get_json()["requests"]
    operators = [r["operator"] for r in records if r["action"] == "entry.sample"]
    assert operators == ["B", "A"]


def test_chinese_operator_survives_http_header(client: FlaskClient) -> None:
    # Header bytes are latin-1 decoded by WSGI; the console must restore UTF-8.
    response = client.post(
        "/api/stop",
        environ_overrides={"HTTP_X_OPERATOR": "王建国"},
    )
    assert response.status_code == 200
    records = client.get("/api/audit/requests").get_json()["requests"]
    assert records[0]["operator"] == "王建国"


def test_malformed_param_value_is_recorded_verbatim(client: FlaskClient) -> None:
    weird = "<script>"
    response = client.post(f"/api/entry/sample?value={weird}")
    assert response.status_code == 400
    record = client.get("/api/audit/requests?failed=1").get_json()["requests"][0]
    assert record["params"]["value"] == weird
    assert record["result"] == "input"
