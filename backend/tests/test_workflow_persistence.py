"""Every offered workflow must survive API validation, persistence and reload."""

from fastapi.testclient import TestClient

from app.editor.intent import WORKFLOW_LABEL
from app.main import app


def test_all_registered_workflows_persist_through_the_notes_api():
    client = TestClient(app)
    headers = {"X-User-Id": "workflow-test", "X-Lang": "en"}
    created = client.post("/api/notes", json={"title": "Workflow persistence"}, headers=headers)
    assert created.status_code == 200, created.text
    note_id = created.json()["id"]
    for workflow in ["", *WORKFLOW_LABEL]:
        task = {"goal": "Explain the launch decision", "reader": "The pilot team",
                "done": "Include alternatives and risks", "workflow": workflow, "source": "user"}
        saved = client.put(f"/api/notes/{note_id}/intent", json=task, headers=headers)
        assert saved.status_code == 200, (workflow, saved.text)
        loaded = client.get(f"/api/notes/{note_id}", headers=headers)
        assert loaded.status_code == 200
        assert loaded.json()["intent"]["workflow"] == workflow
        assert loaded.json()["intent"]["goal"] == task["goal"]

    last_saved = loaded.json()["intent"]
    invalid = client.put(f"/api/notes/{note_id}/intent", json={"workflow": "unknown"}, headers=headers)
    assert invalid.status_code == 422
    assert client.get(f"/api/notes/{note_id}", headers=headers).json()["intent"] == last_saved
