"""Tests for CLI commands."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pulse.cli import cmd_demo_data, cmd_init, cmd_reset


class TestCmdReset:
    def test_reset_clears_data(self, temp_data_dir):
        # Create some dummy files
        (temp_data_dir / "2026-10-10").mkdir(parents=True)
        (temp_data_dir / "2026-10-10" / "events.parquet").touch()

        assert (temp_data_dir / "2026-10-10").exists()

        # Mock args
        class Args:
            data_dir = temp_data_dir

        cmd_reset(Args())

        assert not temp_data_dir.exists()

    def test_reset_nonexistent_dir(self, temp_data_dir):
        # Should not crash if directory doesn't exist
        class Args:
            data_dir = temp_data_dir / "nonexistent"

        cmd_reset(Args())  # Should print message and return


class TestCmdInit:
    def test_init_creates_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / ".pulse" / "config.json"

            with patch("pulse.cli.Path.home", return_value=config_dir):
                class Args:
                    pass

                cmd_init(Args())

            assert config_file.exists()
            with open(config_file) as f:
                config = json.load(f)

            assert "data_dir" in config
            assert "port" in config
            assert config["port"] == 4747

    def test_init_skips_if_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            config_file = config_dir / "config.json"
            config_file.write_text('{"port": 5000}')

            with patch("pulse.cli.Path.home", return_value=config_dir):
                class Args:
                    pass

                cmd_init(Args())

            # Config should not be overwritten
            data = json.loads(config_file.read_text())
            assert data["port"] == 5000


class TestCmdDemoData:
    def test_demo_data_creates_events(self, temp_data_dir):
        class Args:
            data_dir = temp_data_dir

        cmd_demo_data(Args())

        # Check that data directory now contains files
        assert temp_data_dir.exists()
        # Should have created a date folder
        date_folders = list(temp_data_dir.glob("*"))
        assert len(date_folders) > 0
