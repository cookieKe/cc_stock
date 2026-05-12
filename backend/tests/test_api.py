"""Tests for critical API endpoints."""
import json
import pytest


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStocks:
    def test_list_stocks_empty(self, client):
        resp = client.get("/api/stocks/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_stocks_with_data(self, client, sample_stocks):
        resp = client.get("/api/stocks/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3  # only active
        assert len(data["items"]) == 3

    def test_list_stocks_pagination(self, client, sample_stocks):
        resp = client.get("/api/stocks/?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    def test_list_stocks_keyword_filter(self, client, sample_stocks):
        resp = client.get("/api/stocks/?keyword=平安")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "平安银行"

    def test_get_stock_detail(self, client, sample_stocks):
        resp = client.get("/api/stocks/000001")
        assert resp.status_code == 200
        assert resp.json()["name"] == "平安银行"

    def test_get_stock_not_found(self, client, sample_stocks):
        resp = client.get("/api/stocks/999999")
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestDataStatus:
    def test_data_status_empty(self, client):
        resp = client.get("/api/stats/data-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_total"] == 0
        assert data["kline_total"] == 0
        assert data["scan_today"] is None

    def test_data_status_with_data(self, client, sample_stocks, sample_market_data):
        resp = client.get("/api/stats/data-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stock_total"] == 4
        assert data["stock_active"] == 3
        assert data["kline_total"] == 15  # 3 stocks x 5 days
        assert data["kline_stocks"] == 3
        assert data["last_trade_date"] is not None


class TestDataSummary:
    def test_summary_empty(self, client):
        resp = client.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stocks"]["total"] == 0

    def test_summary_with_data(self, client, sample_stocks, sample_market_data):
        resp = client.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stocks"]["total"] == 4
        assert data["stocks"]["active"] == 3
        assert data["klines"]["total_records"] == 15


class TestScans:
    def test_latest_ranking_empty(self, client):
        resp = client.get("/api/scans/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["scan_date"] is None

    def test_latest_ranking_pagination_structure(self, client):
        resp = client.get("/api/scans/latest?limit=10&offset=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_run_scan_no_strategies(self, client):
        """Scan returns error when no strategies are enabled in DB."""
        resp = client.post("/api/scans/run")
        assert resp.status_code == 200
        data = resp.json()
        # No strategies in test DB, should return error
        assert "error" in data

    def test_run_scan_with_stocks(self, client, db_session, sample_stocks, sample_market_data):
        """Scan with strategies seeded in DB."""
        from backend.models.strategy import Strategy

        s1 = Strategy(
            name="momentum", display_name="动量策略",
            class_path="momentum",
            parameters=json.dumps({"lookback_days": 20}), weight=40, is_enabled=True)
        s2 = Strategy(
            name="trend", display_name="趋势策略",
            class_path="trend",
            parameters=json.dumps({}), weight=30, is_enabled=True)
        db_session.add(s1)
        db_session.add(s2)
        db_session.commit()

        resp = client.post("/api/scans/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_scanned" in data
        assert data["total_scanned"] == 3


class TestStocksInit:
    def test_init_when_empty(self, client):
        """Init should handle empty DB gracefully (sync stock list may fail without network)."""
        resp = client.post("/api/stocks/init?max_stocks=2")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
