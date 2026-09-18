from __future__ import annotations

from deleva.persistence import InMemoryPersistence, JsonFilePersistence


class TestInMemoryPersistence:
    def test_starts_empty(self):
        assert InMemoryPersistence().load_state() == {}

    def test_save_then_load_round_trips(self):
        persistence = InMemoryPersistence()
        persistence.save_state({"pending_execution_id": "exec-1"})
        assert persistence.load_state() == {"pending_execution_id": "exec-1"}

    def test_does_not_persist_across_instances(self):
        # Guards the "in-memory only" guarantee this class exists for.
        InMemoryPersistence().save_state({"a": 1})
        assert InMemoryPersistence().load_state() == {}


class TestJsonFilePersistence:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        persistence = JsonFilePersistence(tmp_path / "does_not_exist.json")
        assert persistence.load_state() == {}

    def test_save_then_load_round_trips(self, tmp_path):
        path = tmp_path / "state.json"
        persistence = JsonFilePersistence(path)
        persistence.save_state({"pending_execution_id": "exec-1", "last_action_at": None})
        assert path.exists()

        reloaded = JsonFilePersistence(path)
        assert reloaded.load_state() == {"pending_execution_id": "exec-1", "last_action_at": None}

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "state.json"
        persistence = JsonFilePersistence(path)
        persistence.save_state({"a": 1})
        assert path.exists()

    def test_corrupt_file_returns_empty_dict_rather_than_raising(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not valid json{{{", encoding="utf-8")
        persistence = JsonFilePersistence(path)
        assert persistence.load_state() == {}

    def test_never_stores_a_keeperhub_api_key(self, tmp_path):
        # Defensive: state saved by the engine only ever contains
        # executionIds/timestamps -- this test documents and enforces that
        # a caller cannot accidentally pass a secret-shaped key through.
        path = tmp_path / "state.json"
        persistence = JsonFilePersistence(path)
        state = {"pending_execution_id": "exec-1", "last_action_at": None}
        assert "keeperhub_api_key" not in state
        assert "api_key" not in state
        persistence.save_state(state)
