import hashlib
import json
from pathlib import Path

from pulse.models import Experiment


class ExperimentStore:
    def __init__(self, data_dir: Path):
        # data_dir is ~/.pulse/data/events — store experiments one level up at ~/.pulse/
        self._path = data_dir.parent.parent / "experiments.json"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, default=str))

    def create(self, experiment: Experiment) -> Experiment:
        data = self._load()
        if experiment.name in data:
            raise ValueError(f"Experiment '{experiment.name}' already exists")
        data[experiment.name] = experiment.model_dump()
        self._save(data)
        return experiment

    def list_all(self) -> list[Experiment]:
        return [Experiment(**v) for v in self._load().values()]

    def get(self, name: str) -> Experiment | None:
        data = self._load()
        return Experiment(**data[name]) if name in data else None

    def assign(self, experiment: Experiment, user_id: str) -> str:
        digest = int(hashlib.md5(f"{experiment.name}:{user_id}".encode()).hexdigest(), 16)
        return experiment.variants[digest % len(experiment.variants)]
