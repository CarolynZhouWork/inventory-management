"""
Pytest configuration and fixtures for backend API tests.
"""
import copy
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add server directory to path
server_path = Path(__file__).parent.parent.parent / "server"
sys.path.insert(0, str(server_path))

import mock_data
from main import app


@pytest.fixture(autouse=True)
def restore_mock_data():
    """Restore the in-memory datasets after each test.

    The mock data is module-level mutable state (see server/mock_data.py) shared
    across the whole test session. Endpoints that mutate it in place - e.g.
    POST /api/orders appends to `orders` - would otherwise leak into later tests.
    """
    snapshots = {
        name: copy.deepcopy(getattr(mock_data, name))
        for name in ("inventory_items", "orders", "demand_forecasts", "backlog_items",
                     "recent_transactions", "purchase_orders")
    }
    yield
    for name, original in snapshots.items():
        current = getattr(mock_data, name)
        # Restore contents in place so `main`'s imported references stay valid.
        current[:] = original


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_inventory_item():
    """Sample inventory item for testing."""
    return {
        "id": "1",
        "sku": "PCB-001",
        "name": "Single Layer PCB Assembly",
        "category": "Circuit Boards",
        "warehouse": "San Francisco",
        "quantity_on_hand": 450,
        "reorder_point": 200,
        "unit_cost": 24.99,
        "location": "Warehouse A-12",
        "last_updated": "2025-09-30T10:30:00"
    }


@pytest.fixture
def sample_order():
    """Sample order for testing."""
    return {
        "id": "1",
        "order_number": "ORD-2025-0001",
        "customer": "MegaCorp Industries",
        "items": [
            {
                "sku": "SPR-602",
                "name": "Compression Spring",
                "quantity": 981,
                "unit_price": 89.5
            }
        ],
        "status": "Delivered",
        "warehouse": "Tokyo",
        "category": "Sensors",
        "order_date": "2025-01-08T10:19:00",
        "expected_delivery": "2025-01-21T10:19:00",
        "total_value": 87799.5,
        "actual_delivery": "2025-01-20T10:19:00"
    }


@pytest.fixture
def sample_restock_request():
    """Sample POST /api/orders body for a restocking order."""
    return {
        "customer": "Internal Restock",
        "items": [
            {
                "sku": "WDG-001",
                "name": "Industrial Widget Type A",
                "quantity": 150,
                "unit_price": 12.5,
                "lead_time_days": 10,
            },
            {
                "sku": "CTL-330",
                "name": "Logic Controller Board",
                "quantity": 1,
                "unit_price": 175.0,
                "lead_time_days": 25,
            },
        ],
    }
