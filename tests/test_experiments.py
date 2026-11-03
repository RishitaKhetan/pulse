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


def _rows(*groups):
    """Helper: (variant, users, conversions) tuples -> rows like the query returns."""
    return [{"variant": v, "users": n, "conversions": c} for v, n, c in groups]


class TestAnalyzeResults:
    EXP = Experiment(name="signup_button", variants=["blue", "red"], goal_event="signup")

    def test_clear_winner(self):
        from pulse.experiments import analyze_results

        # blue 10%, red 20%, 1,000 users each: clearly different
        res = analyze_results(self.EXP, _rows(("blue", 1000, 100), ("red", 1000, 200)))

        assert res["winner"] == "red"
        assert res["significant"] is True
        comp = res["comparisons"][0]
        assert comp["variant"] == "red" and comp["vs"] == "blue"
        assert abs(comp["difference"] - 0.10) < 1e-9
        # the 95% range must sit around +10 points and stay above zero
        assert 0 < comp["ci_low"] < 0.10 < comp["ci_high"]
        assert "red converts better than blue" in res["summary"]
        assert "20.0% vs 10.0%" in res["summary"]

    def test_no_clear_winner_yet(self):
        from pulse.experiments import analyze_results

        # 10% vs 11% with 200 users each: could easily be luck
        res = analyze_results(self.EXP, _rows(("blue", 200, 20), ("red", 200, 22)))

        assert res["winner"] is None
        assert res["significant"] is False
        comp = res["comparisons"][0]
        assert comp["ci_low"] < 0 < comp["ci_high"]
        assert res["summary"].startswith("No clear winner yet")

    def test_control_can_win(self):
        from pulse.experiments import analyze_results

        res = analyze_results(self.EXP, _rows(("blue", 1000, 200), ("red", 1000, 100)))

        assert res["winner"] == "blue"
        assert "blue converts better than red" in res["summary"]

    def test_too_few_users(self):
        from pulse.experiments import analyze_results

        res = analyze_results(self.EXP, _rows(("blue", 12, 1), ("red", 9, 3)))

        assert res["winner"] is None
        assert res["summary"].startswith("Too few users so far")

    def test_variants_in_experiment_order_with_control_first(self):
        from pulse.experiments import analyze_results

        exp = Experiment(name="three", variants=["control", "a", "b"], goal_event="buy")
        # the query returns variants in alphabetical order; control must still be the baseline
        res = analyze_results(exp, _rows(("a", 500, 50), ("b", 500, 150), ("control", 500, 50)))

        assert [v["variant"] for v in res["variants"]] == ["control", "a", "b"]
        assert [(c["variant"], c["vs"]) for c in res["comparisons"]] == [("a", "control"), ("b", "control")]
        assert res["winner"] == "b"

    def test_same_answer_every_time(self):
        from pulse.experiments import analyze_results

        rows = _rows(("blue", 300, 30), ("red", 300, 45))
        assert analyze_results(self.EXP, rows) == analyze_results(self.EXP, rows)

    def test_no_data_yet(self):
        from pulse.experiments import analyze_results

        res = analyze_results(self.EXP, [])
        assert res["winner"] is None
        assert res["comparisons"] == []
        assert "No users" in res["summary"]
