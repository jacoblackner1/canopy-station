import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plant_dashboard as p  # noqa: E402


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "CFG_EXAMPLE_PATH", tmp_path / "station.example.json")
    monkeypatch.setattr(p, "CFG_PATH", tmp_path / "station.local.json")
    monkeypatch.setattr(p, "LEGACY_CFG_PATH", tmp_path / "station.json")
    (tmp_path / "station.example.json").write_text(json.dumps({"moistureDry": 600, "autoSeconds": 300}))


def test_local_overrides_example(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    (tmp_path / "station.local.json").write_text(json.dumps({"moistureDry": 640}))
    cfg = p.load_cfg()
    assert cfg["moistureDry"] == 640 and cfg["autoSeconds"] == 300


def test_save_writes_only_diffs(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    cfg = p.load_cfg()
    cfg["moistureWet"] = 222
    p.save_cfg(cfg)
    assert json.loads((tmp_path / "station.local.json").read_text()) == {"moistureWet": 222}
    assert "moistureWet" not in (tmp_path / "station.example.json").read_text()


def test_migrates_legacy(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    (tmp_path / "station.json").write_text(json.dumps({"moistureDry": 655}))
    p.migrate_legacy_cfg()
    assert p.load_cfg()["moistureDry"] == 655
    (tmp_path / "station.json").write_text(json.dumps({"moistureDry": 1}))
    p.migrate_legacy_cfg()  # never overwrites existing local
    assert p.load_cfg()["moistureDry"] == 655
