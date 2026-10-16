"""Tests for CLI commands."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pulse.cli import cmd_demo_data, cmd_init, cmd_reset, cmd_start


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


class TestCmdStartConfig:
    """`pulse start` should read ~/.pulse/config.json, but flags still win."""

    def _run_start(self, home, port=None, no_browser=False, data_dir=None):
        # Fake the home folder and capture what run_server is called with
        class Args:
            pass
        args = Args()
        args.port, args.no_browser, args.data_dir = port, no_browser, data_dir

        with patch("pulse.cli.Path.home", return_value=home), \
             patch("pulse.cli.run_server") as fake_run:
            cmd_start(args)
        return fake_run.call_args.kwargs

    def test_uses_defaults_without_config(self, tmp_path):
        settings = self._run_start(tmp_path)
        assert settings["port"] == 4747
        assert settings["open_browser"] is True

    def test_uses_config_file(self, tmp_path):
        config_file = tmp_path / ".pulse" / "config.json"
        config_file.parent.mkdir()
        config_file.write_text(json.dumps({
            "port": 5000, "open_browser": False, "data_dir": str(tmp_path / "mydata"),
        }))

        settings = self._run_start(tmp_path)
        assert settings["port"] == 5000
        assert settings["open_browser"] is False
        assert settings["data_dir"] == tmp_path / "mydata"

    def test_flags_override_config(self, tmp_path):
        config_file = tmp_path / ".pulse" / "config.json"
        config_file.parent.mkdir()
        config_file.write_text(json.dumps({"port": 5000, "open_browser": True}))

        settings = self._run_start(tmp_path, port=6000, no_browser=True)
        assert settings["port"] == 6000
        assert settings["open_browser"] is False

    def test_broken_config_falls_back_to_defaults(self, tmp_path):
        config_file = tmp_path / ".pulse" / "config.json"
        config_file.parent.mkdir()
        config_file.write_text("{ not valid json")

        settings = self._run_start(tmp_path)
        assert settings["port"] == 4747


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
