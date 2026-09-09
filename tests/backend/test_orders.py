"""
Tests for orders API endpoints (GET /api/orders, GET /api/orders/{id}, POST /api/orders).
"""
from datetime import datetime

import pytest


class TestOrdersEndpoints:
    """Test suite for orders-related endpoints."""

    def test_get_all_orders(self, client):
        """Test getting all orders."""
        response = client.get("/api/orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        first_order = data[0]
        assert "id" in first_order
        assert "order_number" in first_order
        assert "customer" in first_order
        assert "items" in first_order
        assert "status" in first_order
        assert "order_date" in first_order
        assert "expected_delivery" in first_order
        assert "total_value" in first_order

    def test_get_orders_by_warehouse(self, client):
        """Test filtering orders by warehouse."""
        response = client.get("/api/orders?warehouse=Tokyo")
        assert response.status_code == 200

        data = response.json()
        for order in data:
            assert order["warehouse"] == "Tokyo"

    def test_get_orders_by_status(self, client):
        """Test filtering orders by status."""
        response = client.get("/api/orders?status=Delivered")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for order in data:
            assert order["status"].lower() == "delivered"

    def test_get_orders_by_month(self, client):
        """Test filtering orders by month."""
        response = client.get("/api/orders?month=2025-01")
        assert response.status_code == 200

        data = response.json()
        assert len(data) > 0
        for order in data:
            assert "2025-01" in order["order_date"]

    def test_get_order_by_id(self, client):
        """Test getting a specific order by ID."""
        all_orders = client.get("/api/orders").json()
        first_id = all_orders[0]["id"]

        response = client.get(f"/api/orders/{first_id}")
        assert response.status_code == 200
        assert response.json()["id"] == first_id

    def test_get_nonexistent_order(self, client):
        """Test getting an order that doesn't exist."""
        response = client.get("/api/orders/nonexistent-order-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_order_total_value_calculation(self, client):
        """Test that order total values match their line items."""
        data = client.get("/api/orders").json()

        for order in data:
            calculated = sum(
                item["quantity"] * item["unit_price"] for item in order["items"]
            )
            assert abs(order["total_value"] - calculated) < 0.01


class TestCreateOrderEndpoint:
    """Test suite for POST /api/orders (restocking order submission)."""

    def test_create_order_happy_path(self, client, sample_restock_request):
        """Test creating a restocking order returns a well-formed order."""
        response = client.post("/api/orders", json=sample_restock_request)
        assert response.status_code == 201

        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("ORD-")
        assert order["customer"] == "Internal Restock"
        assert isinstance(order["items"], list)
        assert len(order["items"]) == 2
        assert "T" in order["order_date"]
        assert "T" in order["expected_delivery"]
        assert order["actual_delivery"] is None

    def test_create_order_computes_total_value(self, client):
        """Test that total_value is the sum of quantity * unit_price."""
        body = {
            "customer": "Internal Restock",
            "items": [
                {"sku": "GSK-203", "name": "High-Temperature Gasket",
                 "quantity": 100, "unit_price": 8.75, "lead_time_days": 7},
                {"sku": "FLT-405", "name": "Oil Filter Cartridge",
                 "quantity": 10, "unit_price": 15.25, "lead_time_days": 5},
            ],
        }
        order = client.post("/api/orders", json=body).json()
        assert abs(order["total_value"] - (100 * 8.75 + 10 * 15.25)) < 0.01

    def test_create_order_lead_time_uses_slowest_item(self, client):
        """Test expected_delivery is order_date plus the longest line-item lead time."""
        body = {
            "customer": "Internal Restock",
            "items": [
                {"sku": "A", "name": "Fast item", "quantity": 1,
                 "unit_price": 1.0, "lead_time_days": 10},
                {"sku": "B", "name": "Slow item", "quantity": 1,
                 "unit_price": 1.0, "lead_time_days": 25},
            ],
        }
        order = client.post("/api/orders", json=body).json()
        start = datetime.fromisoformat(order["order_date"])
        end = datetime.fromisoformat(order["expected_delivery"])
        assert (end - start).days == 25

    def test_create_order_appears_in_get(self, client, sample_restock_request):
        """Test a submitted order shows up in a subsequent unfiltered GET."""
        created = client.post("/api/orders", json=sample_restock_request).json()
        order_number = created["order_number"]

        listed = client.get("/api/orders").json()
        match = [o for o in listed if o["order_number"] == order_number]
        assert len(match) == 1
        assert match[0]["status"] == "Submitted"

    def test_create_order_excluded_by_status_filter(self, client, sample_restock_request):
        """Test a submitted order is not returned when filtering by another status."""
        created = client.post("/api/orders", json=sample_restock_request).json()
        order_number = created["order_number"]

        delivered = client.get("/api/orders?status=Delivered").json()
        assert all(o["order_number"] != order_number for o in delivered)

    def test_create_order_missing_customer(self, client):
        """Test missing customer field returns a validation error."""
        response = client.post("/api/orders", json={"items": [
            {"sku": "A", "name": "X", "quantity": 1, "unit_price": 1.0}
        ]})
        assert response.status_code == 422

    def test_create_order_empty_items(self, client):
        """Test an empty items list is rejected."""
        response = client.post("/api/orders", json={"customer": "X", "items": []})
        assert response.status_code == 422

    def test_create_order_bad_quantity_type(self, client):
        """Test a non-numeric quantity returns a validation error."""
        response = client.post("/api/orders", json={
            "customer": "X",
            "items": [{"sku": "A", "name": "X", "quantity": "lots", "unit_price": 1.0}],
        })
        assert response.status_code == 422
