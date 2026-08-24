"""
Tests for restocking order API endpoints.
"""
import re
from datetime import datetime

import pytest


# Mirrors CATEGORY_LEAD_TIME_DAYS in server/main.py. Duplicated deliberately so a
# change to the production lookup has to be made consciously in both places.
EXPECTED_LEAD_TIMES = {
    "Circuit Boards": 21,
    "Sensors": 14,
    "Actuators": 28,
    "Controllers": 18,
    "Power Supplies": 10,
}

ORDER_NUMBER_PATTERN = re.compile(r"^RST-\d{4}-\d{4}$")


def build_order_payload(client, sku_count=2, budget=1_000_000.0):
    """Build a valid restocking order payload from real inventory items."""
    inventory = client.get("/api/inventory").json()
    chosen = inventory[:sku_count]

    return {
        "budget": budget,
        "items": [
            {
                "sku": item["sku"],
                "name": item["name"],
                "quantity": 10,
                "unit_price": item["unit_cost"],
            }
            for item in chosen
        ],
    }


class TestRestockingOrderEndpoints:
    """Test suite for restocking order endpoints."""

    def test_get_all_restocking_orders(self, client):
        """Test getting all restocking orders."""
        response = client.get("/api/restocking-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_restocking_order(self, client):
        """Test submitting a restocking order."""
        payload = build_order_payload(client)

        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 200

        order = response.json()
        assert "id" in order
        assert "order_number" in order
        assert "items" in order
        assert "status" in order
        assert "submitted_date" in order
        assert "expected_delivery" in order
        assert "lead_time_days" in order
        assert "total_value" in order
        assert "budget" in order

        assert order["status"] == "Submitted"
        assert order["budget"] == payload["budget"]
        assert len(order["items"]) == len(payload["items"])

    def test_created_order_number_format(self, client):
        """Test that the generated order number follows the RST-YYYY-#### format."""
        response = client.post("/api/restocking-orders", json=build_order_payload(client))
        assert response.status_code == 200

        order_number = response.json()["order_number"]
        assert ORDER_NUMBER_PATTERN.match(order_number), order_number

    def test_created_order_does_not_collide_with_customer_orders(self, client):
        """Test that restocking order numbers never clash with the ORD- series."""
        response = client.post("/api/restocking-orders", json=build_order_payload(client))
        restock_number = response.json()["order_number"]

        customer_numbers = {o["order_number"] for o in client.get("/api/orders").json()}
        assert restock_number not in customer_numbers
        assert restock_number.startswith("RST-")

    def test_created_order_total_value_calculation(self, client):
        """Test that total value is the sum of the submitted line items."""
        payload = build_order_payload(client, sku_count=3)

        response = client.post("/api/restocking-orders", json=payload)
        order = response.json()

        expected_total = sum(
            item["quantity"] * item["unit_price"] for item in payload["items"]
        )
        assert abs(order["total_value"] - expected_total) < 0.01

    def test_created_order_lead_time_is_max_of_categories(self, client):
        """Test that lead time is the slowest category among the ordered items."""
        inventory = client.get("/api/inventory").json()
        by_sku = {item["sku"]: item for item in inventory}

        payload = build_order_payload(client, sku_count=4)
        response = client.post("/api/restocking-orders", json=payload)
        order = response.json()

        expected = max(
            EXPECTED_LEAD_TIMES[by_sku[item["sku"]]["category"]]
            for item in payload["items"]
        )
        assert order["lead_time_days"] == expected

    def test_created_order_expected_delivery_matches_lead_time(self, client):
        """Test that expected delivery is lead_time_days after the submitted date."""
        response = client.post("/api/restocking-orders", json=build_order_payload(client))
        order = response.json()

        submitted = datetime.fromisoformat(order["submitted_date"])
        delivery = datetime.fromisoformat(order["expected_delivery"])

        assert (delivery - submitted).days == order["lead_time_days"]
        assert delivery > submitted

    def test_created_order_appears_in_list(self, client):
        """Test that a submitted order is retrievable afterwards."""
        response = client.post("/api/restocking-orders", json=build_order_payload(client))
        created_id = response.json()["id"]

        listed = client.get("/api/restocking-orders").json()
        assert created_id in [order["id"] for order in listed]

    def test_order_numbers_are_unique(self, client):
        """Test that two submissions receive distinct order numbers."""
        first = client.post("/api/restocking-orders", json=build_order_payload(client)).json()
        second = client.post("/api/restocking-orders", json=build_order_payload(client)).json()

        assert first["order_number"] != second["order_number"]
        assert first["id"] != second["id"]

    def test_restocking_orders_are_newest_first(self, client):
        """Test that the most recently submitted order is returned first."""
        created = client.post("/api/restocking-orders", json=build_order_payload(client)).json()

        listed = client.get("/api/restocking-orders").json()
        assert listed[0]["id"] == created["id"]

    def test_created_order_item_structure(self, client):
        """Test that submitted line items keep their full structure."""
        response = client.post("/api/restocking-orders", json=build_order_payload(client))
        order = response.json()

        for item in order["items"]:
            assert "sku" in item
            assert "name" in item
            assert "quantity" in item
            assert "unit_price" in item
            assert isinstance(item["quantity"], int)
            assert isinstance(item["unit_price"], (int, float))
            assert item["quantity"] > 0

    def test_create_restocking_order_rejects_empty_items(self, client):
        """Test that an order with no items is rejected."""
        response = client.post("/api/restocking-orders", json={"budget": 500.0, "items": []})
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "at least one item" in data["detail"].lower()

    def test_create_restocking_order_rejects_missing_field(self, client):
        """Test that a payload missing a required field fails validation."""
        response = client.post(
            "/api/restocking-orders",
            json={"items": [{"sku": "PCB-001", "name": "x", "quantity": 1, "unit_price": 1.0}]},
        )
        assert response.status_code == 422

    def test_unknown_sku_falls_back_to_default_lead_time(self, client):
        """Test that a SKU with no inventory record still gets a usable lead time."""
        payload = {
            "budget": 100.0,
            "items": [{"sku": "DOES-NOT-EXIST", "name": "Mystery Part", "quantity": 1, "unit_price": 5.0}],
        }
        response = client.post("/api/restocking-orders", json=payload)
        assert response.status_code == 200
        assert response.json()["lead_time_days"] == 14

    def test_submitting_does_not_affect_customer_orders(self, client):
        """Test that restocking submissions leave the customer order data untouched."""
        before = len(client.get("/api/orders").json())

        client.post("/api/restocking-orders", json=build_order_payload(client))

        assert len(client.get("/api/orders").json()) == before
        # The backlog endpoint joins against purchase_orders; make sure it still works
        assert client.get("/api/backlog").status_code == 200


class TestRestockingDataIntegrity:
    """Guards the inventory/forecast join the restocking recommendations rely on."""

    def test_all_forecast_skus_exist_in_inventory(self, client):
        """Test that every demand forecast SKU resolves to an inventory item."""
        forecasts = client.get("/api/demand").json()
        inventory_skus = {item["sku"] for item in client.get("/api/inventory").json()}

        missing = [f["item_sku"] for f in forecasts if f["item_sku"] not in inventory_skus]
        assert not missing, f"Forecast SKUs with no inventory record: {missing}"

    def test_every_inventory_category_has_a_lead_time(self, client):
        """Test that no inventory category silently falls back to the default lead time."""
        categories = {item["category"] for item in client.get("/api/inventory").json()}
        assert categories <= set(EXPECTED_LEAD_TIMES)

    def test_some_forecast_items_need_restocking(self, client):
        """Test that the fixtures produce a non-empty recommendation set."""
        forecasts = client.get("/api/demand").json()
        by_sku = {item["sku"]: item for item in client.get("/api/inventory").json()}

        needing_restock = [
            f["item_sku"]
            for f in forecasts
            if f["forecasted_demand"] - by_sku[f["item_sku"]]["quantity_on_hand"] > 0
        ]
        assert len(needing_restock) > 0
