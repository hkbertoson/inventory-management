"""
Tests for task API endpoints.
"""
import pytest

from mock_data import tasks


@pytest.fixture(autouse=True)
def reset_tasks():
    """Keep tests independent - the API appends to a module-level list."""
    snapshot = list(tasks)
    yield
    tasks[:] = snapshot


def build_task_payload(title="Review Q4 inventory levels", priority="high", due_date="2025-12-01"):
    """Build a valid create-task payload."""
    return {"title": title, "priority": priority, "dueDate": due_date}


class TestTaskEndpoints:
    """Test suite for task endpoints."""

    def test_get_all_tasks(self, client):
        """Test getting all tasks."""
        response = client.get("/api/tasks")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_task(self, client):
        """Test creating a task."""
        response = client.post("/api/tasks", json=build_task_payload())
        assert response.status_code == 200

        task = response.json()
        assert "id" in task
        assert task["title"] == "Review Q4 inventory levels"
        assert task["priority"] == "high"
        assert task["dueDate"] == "2025-12-01"
        assert task["status"] == "pending"

    def test_created_task_uses_string_id(self, client):
        """Task ids must be strings so they never collide with the client's integer mock ids."""
        response = client.post("/api/tasks", json=build_task_payload())
        task = response.json()

        assert isinstance(task["id"], str)
        assert task["id"].startswith("api-")

    def test_task_uses_camelcase_due_date(self, client):
        """The client binds task.dueDate directly, so the field name is part of the contract."""
        client.post("/api/tasks", json=build_task_payload())

        response = client.get("/api/tasks")
        data = response.json()

        assert len(data) > 0
        assert "dueDate" in data[0]
        assert "due_date" not in data[0]

    def test_created_task_appears_first(self, client):
        """Test that newly created tasks are returned newest first."""
        client.post("/api/tasks", json=build_task_payload(title="Older task"))
        client.post("/api/tasks", json=build_task_payload(title="Newer task"))

        response = client.get("/api/tasks")
        data = response.json()

        assert data[0]["title"] == "Newer task"
        assert data[1]["title"] == "Older task"

    def test_create_task_defaults_priority(self, client):
        """Test that priority defaults to medium when omitted."""
        response = client.post(
            "/api/tasks",
            json={"title": "Approve Tokyo warehouse orders", "dueDate": "2025-11-15"}
        )
        assert response.status_code == 200
        assert response.json()["priority"] == "medium"

    def test_create_task_trims_title(self, client):
        """Test that surrounding whitespace is stripped from the title."""
        response = client.post("/api/tasks", json=build_task_payload(title="  Padded title  "))
        assert response.status_code == 200
        assert response.json()["title"] == "Padded title"

    def test_create_task_blank_title(self, client):
        """Test that a blank title is rejected."""
        response = client.post("/api/tasks", json=build_task_payload(title="   "))
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "empty" in data["detail"].lower()

    def test_create_task_missing_due_date(self, client):
        """Test that a missing dueDate fails validation."""
        response = client.post("/api/tasks", json={"title": "No due date"})
        assert response.status_code == 422

    def test_toggle_task(self, client):
        """Test toggling a task between pending and completed."""
        task_id = client.post("/api/tasks", json=build_task_payload()).json()["id"]

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.patch(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_toggle_nonexistent_task(self, client):
        """Test toggling a task that doesn't exist."""
        response = client.patch("/api/tasks/nonexistent-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_delete_task(self, client):
        """Test deleting a task."""
        task_id = client.post("/api/tasks", json=build_task_payload()).json()["id"]

        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        remaining = client.get("/api/tasks").json()
        assert all(task["id"] != task_id for task in remaining)

    def test_delete_nonexistent_task(self, client):
        """Test deleting a task that doesn't exist."""
        response = client.delete("/api/tasks/nonexistent-999")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_task_structure(self, client):
        """Test that every task exposes the full documented structure."""
        client.post("/api/tasks", json=build_task_payload())

        data = client.get("/api/tasks").json()

        for task in data:
            assert isinstance(task["id"], str)
            assert isinstance(task["title"], str)
            assert isinstance(task["dueDate"], str)
            assert task["priority"] in ["high", "medium", "low"]
            assert task["status"] in ["pending", "completed"]
