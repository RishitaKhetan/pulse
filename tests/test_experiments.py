"""Tests for experiment storage and assignment."""
from pulse.experiments import ExperimentStore
from pulse.models import Experiment


class TestExperimentStore:
    def test_experiments_file_stays_inside_data_folder(self, temp_data_dir):
        # Bug 3: the file used to go two folders above the data folder,
        # e.g. --data-dir C:\mydata\events wrote to C:\experiments.json
        data_dir = temp_data_dir / "mydata" / "events"
        store = ExperimentStore(data_dir=data_dir)

        store.create(Experiment(name="button_color", goal_event="signup"))

        assert (data_dir / "experiments.json").exists()
        # Nothing should be written next to or above the data folder
        assert list(temp_data_dir.iterdir()) == [temp_data_dir / "mydata"]
        assert list((temp_data_dir / "mydata").iterdir()) == [data_dir]

    def test_saved_experiment_can_be_read_back(self, temp_data_dir):
        store = ExperimentStore(data_dir=temp_data_dir)
        store.create(Experiment(name="button_color", goal_event="signup"))

        # A fresh store (like after a restart) finds the same experiment
        again = ExperimentStore(data_dir=temp_data_dir)
        exp = again.get("button_color")
        assert exp is not None
        assert exp.goal_event == "signup"

    def test_same_user_always_gets_same_variant(self, temp_data_dir):
        store = ExperimentStore(data_dir=temp_data_dir)
        exp = Experiment(name="button_color", goal_event="signup")

        first = store.assign(exp, "alice")
        assert all(store.assign(exp, "alice") == first for _ in range(20))
        assert first in exp.variants
