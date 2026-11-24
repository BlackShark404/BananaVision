"""Packaged model fallback for the YOLO classifier, the same rule as the spoilage model.

A station keeps its own checkpoint in app/ml/weights/ (git-ignored). When the configured
default is missing there, the backend uses the copy packaged in Git (app/ml/), so a fresh
checkout still classifies. A missing custom path stays missing, so a wrong setting is visible.
Uses temporary folders only.
"""

from pathlib import Path

from app.services import backup_archive
from app.services.classification import PACKAGED_MODEL, resolve_model_path

DEFAULT = "app/ml/weights/banana_yolo26m.pt"


def app_dir(tmp_path, *, station=False, packaged=False):
    root = tmp_path / "app"
    (root / "ml" / "weights").mkdir(parents=True)
    if station:
        (root / "ml" / "weights" / "banana_yolo26m.pt").write_bytes(b"station")
    if packaged:
        (root / "ml" / PACKAGED_MODEL).write_bytes(b"packaged")
    return root


def test_missing_default_uses_the_station_copy_then_the_packaged_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the relative default does not exist from here
    both = app_dir(tmp_path / "a", station=True, packaged=True)
    assert resolve_model_path(DEFAULT, both) == both / "ml" / "weights" / "banana_yolo26m.pt"
    packaged_only = app_dir(tmp_path / "b", packaged=True)
    assert resolve_model_path(DEFAULT, packaged_only) == packaged_only / "ml" / PACKAGED_MODEL
    # The config default (nano name) falls back the same way.
    assert resolve_model_path("app/ml/weights/banana_yolov26n.pt", packaged_only) == (
        packaged_only / "ml" / PACKAGED_MODEL)
    neither = app_dir(tmp_path / "c")
    assert resolve_model_path(DEFAULT, neither) == Path(DEFAULT)


def test_an_existing_or_custom_path_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    packaged = app_dir(tmp_path / "a", packaged=True)
    (tmp_path / "app" / "ml" / "weights").mkdir(parents=True)
    (tmp_path / DEFAULT).write_bytes(b"configured")
    assert resolve_model_path(DEFAULT, packaged) == Path(DEFAULT)
    custom = "app/ml/weights/retrained_v3.pt"
    assert resolve_model_path(custom, packaged) == Path(custom)
    absolute = str(tmp_path / "missing" / "model.pt")
    assert resolve_model_path(absolute, packaged) == Path(absolute)


def test_backup_records_the_classifier_file_the_backend_loads(tmp_path, monkeypatch):
    packaged = app_dir(tmp_path, packaged=True)
    monkeypatch.chdir(tmp_path / "app")  # nothing at the relative default
    monkeypatch.setattr(
        "app.services.classification.resolve_model_path",
        lambda configured, base=None: resolve_model_path(configured, packaged),
    )
    monkeypatch.setattr(backup_archive, "_hash_file", lambda path: f"sha:{Path(path).name}")
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "yolo_model_path", DEFAULT)
    classifier = backup_archive.model_prerequisites()["classifier"]
    assert classifier == {"filename": PACKAGED_MODEL, "sha256": f"sha:{PACKAGED_MODEL}"}
