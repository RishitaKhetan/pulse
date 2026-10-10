"""Tests for data models and validation."""
import pytest
from pydantic import ValidationError

from pulse.models import Event, Experiment


class TestEvent:
    def test_event_creation(self):
        event = Event(event_name="click", user_id="alice")
        assert event.event_name == "click"
        assert event.user_id == "alice"
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_event_with_properties(self):
        event = Event(
            event_name="click",
            user_id="alice",
            properties={"button": "signup", "page": "/home"}
        )
        assert event.properties["button"] == "signup"


class TestExperiment:
    def test_experiment_creation(self):
        exp = Experiment(
            name="test-exp",
            variants=["control", "treatment"],
            goal_event="signup"
        )
        assert exp.name == "test-exp"
        assert len(exp.variants) == 2

    def test_experiment_invalid_name(self):
        with pytest.raises(ValidationError):
            Experiment(
                name="test exp!",  # Invalid: has space and special char
                variants=["control", "treatment"],
                goal_event="signup"
            )

    def test_experiment_needs_two_variants(self):
        with pytest.raises(ValidationError):
            Experiment(
                name="test-exp",
                variants=["control"],  # Only one variant
                goal_event="signup"
            )
