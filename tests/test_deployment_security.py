import subprocess
from pathlib import Path

import yaml


def test_parser_worker_is_restricted():
    rendered = subprocess.check_output(
        ["docker", "compose", "config"], text=True, encoding="utf-8"
    )
    config = yaml.safe_load(rendered)
    worker = config["services"]["parser-worker"]
    assert worker["read_only"] is True
    assert worker["cap_drop"] == ["ALL"]
    assert worker["security_opt"] == ["no-new-privileges:true"]
    assert worker["pids_limit"] <= 256
    assert worker.get("ports") in (None, [])
    assert config["networks"]["parser-internal"]["internal"] is True
    assert set(worker["networks"]) == {"parser-internal"}


def test_parser_worker_installs_only_parser_dependencies():
    dockerfile = Path("deploy/parser-worker.Dockerfile").read_text(encoding="utf-8")
    assert "parser-requirements.txt" in dockerfile
    assert "pip install --no-cache-dir ." not in dockerfile
