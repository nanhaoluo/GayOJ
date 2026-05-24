from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.config import JUDGE_NODE_HEARTBEAT_TTL_SECONDS, JUDGE_NODE_TOKEN
from app.db import Repository, now
from app.models import JudgeNode


WORKER_HEADERS = {"x-judge-node-token": JUDGE_NODE_TOKEN}


def heartbeat_payload(**overrides):
    payload = {
        "id": "node-p4",
        "name": "p4-worker-a",
        "status": "online",
        "languages": ["python", "cpp"],
        "queue_depth": 2,
        "load": 0.42,
    }
    payload.update(overrides)
    return payload


def test_judge_node_heartbeat_registers_node_and_admin_can_update_status(
    client: TestClient,
    auth_headers,
) -> None:
    assert client.post("/api/v1/judge/nodes/heartbeat", json=heartbeat_payload()).status_code == 401

    heartbeat = client.post(
        "/api/v1/judge/nodes/heartbeat",
        headers=WORKER_HEADERS,
        json=heartbeat_payload(languages=["Python", "python", "CPP"]),
    )
    assert heartbeat.status_code == 200, heartbeat.text
    node = heartbeat.json()
    assert node["id"] == "node-p4"
    assert node["status"] == "online"
    assert node["languages"] == ["python", "cpp"]
    assert node["queue_depth"] == 2
    assert node["load"] == 0.42

    assert client.patch(
        "/api/v1/admin/judge-nodes/node-p4",
        headers=auth_headers("judge"),
        json={"status": "draining"},
    ).status_code == 403

    updated = client.patch(
        "/api/v1/admin/judge-nodes/node-p4",
        headers=auth_headers("admin"),
        json={"status": "draining"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "draining"

    nodes = client.get("/api/v1/admin/judge-nodes", headers=auth_headers("admin"))
    assert nodes.status_code == 200, nodes.text
    p4_node = next(item for item in nodes.json() if item["id"] == "node-p4")
    assert p4_node["status"] == "draining"


def test_stale_judge_node_heartbeat_is_reported_offline(
    client: TestClient,
    auth_headers,
    store: Repository,
) -> None:
    store.update_judge_node(
        JudgeNode(
            id="node-stale",
            name="stale-worker",
            status="online",
            languages=["python"],
            queue_depth=0,
            load=0.1,
            last_heartbeat=now() - timedelta(seconds=JUDGE_NODE_HEARTBEAT_TTL_SECONDS + 5),
        )
    )

    nodes = client.get("/api/v1/admin/judge-nodes", headers=auth_headers("admin"))

    assert nodes.status_code == 200, nodes.text
    stale = next(item for item in nodes.json() if item["id"] == "node-stale")
    assert stale["status"] == "offline"


def test_worker_claims_queued_code_submission_without_api_local_judging(
    client: TestClient,
    auth_headers,
) -> None:
    heartbeat = client.post(
        "/api/v1/judge/nodes/heartbeat",
        headers=WORKER_HEADERS,
        json=heartbeat_payload(id="node-claim", name="claim-worker", languages=["python"], queue_depth=0, load=0.05),
    )
    assert heartbeat.status_code == 200, heartbeat.text

    submission = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "a, b = map(int, input().split())\nprint(a + b)\n"},
    )
    assert submission.status_code == 200, submission.text
    queued = submission.json()
    assert queued["status"] == "queued"
    assert queued["queue_job_id"]
    assert queued["queued_at"]
    assert queued["judged_at"] is None
    assert queued["details"] == []

    monitor = client.get("/api/v1/judge/monitor", headers=auth_headers("judge"))
    assert monitor.status_code == 200, monitor.text
    assert monitor.json()["queue"]["pending"] >= 1
    assert monitor.json()["queue"]["depth"] >= 1

    claimed = client.post("/api/v1/judge/nodes/node-claim/claim", headers=WORKER_HEADERS)
    assert claimed.status_code == 200, claimed.text
    payload = claimed.json()
    assert payload["node"]["id"] == "node-claim"
    assert payload["job"]["id"] == queued["queue_job_id"]
    assert payload["job"]["status"] == "leased"
    assert payload["job"]["assigned_node_id"] == "node-claim"
    assert payload["submission"]["id"] == queued["id"]
    assert payload["submission"]["status"] == "judging"
    assert payload["submission"]["score"] == 0
    assert payload["submission"]["judged_at"] is None
    assert payload["submission"]["details"] == []

    public_problem = client.get("/api/v1/problems/P1002")
    assert public_problem.status_code == 200
    assert "judge_config" not in public_problem.json()


def test_draining_or_offline_node_cannot_claim_work(client: TestClient, auth_headers) -> None:
    heartbeat = client.post(
        "/api/v1/judge/nodes/heartbeat",
        headers=WORKER_HEADERS,
        json=heartbeat_payload(id="node-draining", status="draining", languages=["python"]),
    )
    assert heartbeat.status_code == 200, heartbeat.text

    submission = client.post(
        "/api/v1/problems/P1001/submit-code",
        headers=auth_headers("alice"),
        json={"language": "python", "source_code": "print(3)\n"},
    )
    assert submission.status_code == 200, submission.text

    claimed = client.post("/api/v1/judge/nodes/node-draining/claim", headers=WORKER_HEADERS)
    assert claimed.status_code == 409
