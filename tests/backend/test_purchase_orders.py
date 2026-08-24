"""
Tests for purchase order API endpoints.
"""
import re

import pytest

from mock_data import purchase_orders

PO_ID_PATTERN = re.compile(r"^PO-\d{4}-\d{4}$")


@pytest.fixture(autouse=True)
def reset_purchase_orders():
    """Keep tests independent - the API appends to a module-level list."""
    snapshot = [dict(po) for po in purchase_orders]
    yield
    purchase_orders[:] = snapshot


def find_backlog_item_without_po(client):
    """Return a backlog item that has no purchase order raised against it yet."""
    backlog = client.get("/api/backlog").json()
    item = next((item for item in backlog if not item["purchase_order_id"]), None)
    assert item is not None, "Expected at least one backlog item without a purchase order"
    return item


def build_po_payload(backlog_item_id, quantity=100, unit_cost=45.0):
    """Build a valid create-purchase-order payload."""
    return {
        "backlog_item_id": backlog_item_id,
        "supplier_name": "Precision Parts Co.",
        "quantity": quantity,
        "unit_cost": unit_cost,
        "expected_delivery_date": "2025-12-15",
        "notes": "Expedite if possible",
    }


class TestPurchaseOrderEndpoints:
    """Test suite for purchase order endpoints."""

    def test_create_purchase_order(self, client):
        """Test raising a purchase order against a backlog item."""
        item = find_backlog_item_without_po(client)

        response = client.post("/api/purchase-orders", json=build_po_payload(item["id"]))
        assert response.status_code == 200

        po = response.json()
        assert PO_ID_PATTERN.match(po["id"])
        assert po["backlog_item_id"] == item["id"]
        assert po["supplier_name"] == "Precision Parts Co."
        assert po["quantity"] == 100
        assert po["unit_cost"] == 45.0
        assert po["expected_delivery_date"] == "2025-12-15"
        assert po["status"] == "Pending"
        assert po["notes"] == "Expedite if possible"
        assert "T" in po["created_date"]

    def test_create_purchase_order_without_notes(self, client):
        """Test that notes are optional."""
        item = find_backlog_item_without_po(client)
        payload = build_po_payload(item["id"])
        del payload["notes"]

        response = client.post("/api/purchase-orders", json=payload)
        assert response.status_code == 200
        assert response.json()["notes"] is None

    def test_create_duplicate_purchase_order(self, client):
        """Test that a backlog item can only have one purchase order."""
        item = find_backlog_item_without_po(client)
        client.post("/api/purchase-orders", json=build_po_payload(item["id"]))

        response = client.post("/api/purchase-orders", json=build_po_payload(item["id"]))
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "already has" in data["detail"].lower()

    def test_create_purchase_order_nonexistent_backlog_item(self, client):
        """Test raising a purchase order against a backlog item that doesn't exist."""
        response = client.post("/api/purchase-orders", json=build_po_payload("nonexistent-999"))
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_create_purchase_order_zero_quantity(self, client):
        """Test that quantity must be greater than zero."""
        item = find_backlog_item_without_po(client)

        response = client.post(
            "/api/purchase-orders", json=build_po_payload(item["id"], quantity=0)
        )
        assert response.status_code == 400
        assert "quantity" in response.json()["detail"].lower()

    def test_create_purchase_order_negative_unit_cost(self, client):
        """Test that unit cost cannot be negative."""
        item = find_backlog_item_without_po(client)

        response = client.post(
            "/api/purchase-orders", json=build_po_payload(item["id"], unit_cost=-1.0)
        )
        assert response.status_code == 400
        assert "unit cost" in response.json()["detail"].lower()

    def test_get_purchase_order_by_backlog_item(self, client):
        """Test fetching a purchase order by its backlog item id."""
        item = find_backlog_item_without_po(client)
        created = client.post("/api/purchase-orders", json=build_po_payload(item["id"])).json()

        response = client.get(f"/api/purchase-orders/{item['id']}")
        assert response.status_code == 200

        po = response.json()
        assert po["id"] == created["id"]
        assert po["backlog_item_id"] == item["id"]

    def test_get_nonexistent_purchase_order(self, client):
        """Test fetching a purchase order for a backlog item that has none."""
        response = client.get("/api/purchase-orders/nonexistent-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "no purchase order" in data["detail"].lower()

    def test_purchase_order_value_types(self, client):
        """Test that purchase order numeric fields have proper types."""
        item = find_backlog_item_without_po(client)
        po = client.post("/api/purchase-orders", json=build_po_payload(item["id"])).json()

        assert isinstance(po["quantity"], int)
        assert isinstance(po["unit_cost"], (int, float))
        assert po["quantity"] > 0
        assert po["unit_cost"] >= 0


class TestBacklogPurchaseOrderLink:
    """Test suite for the purchase order fields exposed on backlog items."""

    def test_backlog_exposes_purchase_order_id(self, client):
        """Test that a backlog item reports the id of its purchase order."""
        item = find_backlog_item_without_po(client)
        created = client.post("/api/purchase-orders", json=build_po_payload(item["id"])).json()

        backlog = client.get("/api/backlog").json()
        updated = next(b for b in backlog if b["id"] == item["id"])

        assert updated["purchase_order_id"] == created["id"]
        assert updated["has_purchase_order"] is True

    def test_backlog_purchase_order_id_null_without_po(self, client):
        """Test that a backlog item without a purchase order reports a null id."""
        item = find_backlog_item_without_po(client)

        assert item["purchase_order_id"] is None
        assert item["has_purchase_order"] is False

    def test_backlog_flag_matches_id(self, client):
        """Test that the boolean flag and the id field never disagree."""
        backlog = client.get("/api/backlog").json()

        for item in backlog:
            assert item["has_purchase_order"] == (item["purchase_order_id"] is not None)
