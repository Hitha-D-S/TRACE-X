"""API integration tests using TestClient."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.detection.pipeline import reset_pipeline


@pytest.fixture(autouse=True)
def reset_state():
    reset_pipeline()
    yield
    reset_pipeline()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_metrics_returns_counts(self, client):
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "transactions_processed" in data
        assert "alerts_total" in data


class TestTransactionIngestion:
    def test_ingest_single_transaction(self, client):
        payload = {
            "source_account_id": "ACC-TEST-001",
            "destination_account_id": "ACC-TEST-002",
            "amount": "50000.00",
            "currency": "INR",
            "transaction_type": "NEFT",
        }
        resp = client.post("/api/v1/transactions", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert "final_risk_score" in data
        assert 0 <= data["final_risk_score"] <= 100

    def test_ingest_validates_same_account(self, client):
        payload = {
            "source_account_id": "ACC-SAME",
            "destination_account_id": "ACC-SAME",
            "amount": "1000",
        }
        resp = client.post("/api/v1/transactions", json=payload)
        assert resp.status_code == 422  # validation error

    def test_ingest_validates_negative_amount(self, client):
        payload = {
            "source_account_id": "ACC-A",
            "destination_account_id": "ACC-B",
            "amount": "-100",
        }
        resp = client.post("/api/v1/transactions", json=payload)
        assert resp.status_code == 422

    def test_batch_ingest(self, client):
        payload = {
            "transactions": [
                {
                    "source_account_id": f"ACC-BATCH-{i}",
                    "destination_account_id": f"ACC-BATCH-{i+1}",
                    "amount": str(1000 * (i + 1)),
                }
                for i in range(5)
            ]
        }
        resp = client.post("/api/v1/transactions/batch", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["processed"] == 5

    def test_list_transactions(self, client):
        # Ingest a few first
        for i in range(3):
            client.post("/api/v1/transactions", json={
                "source_account_id": f"LST-{i}",
                "destination_account_id": f"LST-{i+10}",
                "amount": "1000",
            })

        resp = client.get("/api/v1/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert "transactions" in data
        assert "total" in data


class TestAlertEndpoints:
    def test_list_alerts_empty(self, client):
        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    def test_get_nonexistent_alert(self, client):
        resp = client.get("/api/v1/alerts/ALT-NOTEXIST")
        assert resp.status_code == 404


class TestGraphEndpoints:
    def test_network_endpoint_returns_structure(self, client):
        # Ingest some transactions
        for i in range(5):
            client.post("/api/v1/transactions", json={
                "source_account_id": f"GRF-{i}",
                "destination_account_id": f"GRF-{i+1}",
                "amount": "10000",
            })

        resp = client.get("/api/v1/graph/network?use_cache=false")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data


class TestDatasetEndpoints:
    def test_list_datasets(self, client):
        resp = client.get("/api/v1/datasets")
        assert resp.status_code == 200
        data = resp.json()
        assert "datasets" in data


class TestAuthEndpoints:
    def test_login_valid_credentials(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@tracex.demo",
            "password": "tracex-admin",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["role"] == "admin"

    def test_login_invalid_credentials(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 401
