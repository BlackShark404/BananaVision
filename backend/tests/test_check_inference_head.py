"""The head check reads checkpoints without running their pickles."""

import io
import pickle
import zipfile
from pathlib import Path

import pytest

from scripts import check_inference_head as check

WEIGHTS = Path(__file__).resolve().parents[1] / "yolo26n.pt"


def torch_like_checkpoint(path, payload, protocol=2):
    """A zip holding data.pkl, the layout torch.save writes."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("model/data.pkl", pickle.dumps(payload, protocol=protocol))
    return path


def payload(head_state):
    """Key order as Ultralytics writes it: the model (with its YAML) before train_args."""
    modules = {"cv2": 1, "cv3": 2}
    modules.update(head_state.pop("branches", {}))
    return {
        "date": "2026-10-20T10:00:00", "version": "8.4.148",
        "model": {"yaml": {"end2end": False, "nms": True}, "_modules": modules, **head_state},
        "train_args": {"end2end": True, "nms": False, "imgsz": 640},
    }


@pytest.mark.parametrize("protocol", [2, 4])
def test_static_scan_reads_metadata_and_head_branches(tmp_path, protocol):
    path = torch_like_checkpoint(
        tmp_path / "w.pt", payload({"branches": {"one2one_cv2": 3}}), protocol,
    )
    report = check.run_static(path)
    assert report["ultralytics_version"] == "8.4.148"
    assert report["date"] == "2026-10-20T10:00:00"
    assert report["train_end2end"] is True and report["train_nms"] is False
    assert report["has_one_to_one_branch"] is True
    assert report["stored_head_choice"] == "absent"
    assert report["expected_checkpoint_head_8_4_40"].startswith("one_to_one")


def test_static_scan_sees_a_stored_head_choice(tmp_path):
    path = torch_like_checkpoint(
        tmp_path / "w.pt", payload({"branches": {"one2one_cv2": 3}, "_end2end": False}),
    )
    report = check.run_static(path)
    assert report["stored_head_choice"] is False
    assert report["expected_checkpoint_head_8_4_40"] == "one_to_many_nms (stored)"


def test_static_scan_never_executes_the_pickle(tmp_path):
    class Boom:
        def __reduce__(self):
            return (exec, ("raise SystemExit('executed')",))

    path = tmp_path / "evil.pt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("x/data.pkl", pickle.dumps({"version": "1", "obj": Boom()}))
    report = check.run_static(path)  # would raise SystemExit if anything ran
    assert report["ultralytics_version"] == "1"


def test_static_scan_rejects_missing_or_foreign_files(tmp_path):
    with pytest.raises(check.CheckError):
        check.run_static(tmp_path / "missing.pt")
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", "no model")
    with pytest.raises(check.CheckError):
        check.run_static(empty)


def test_cli_writes_a_manila_timestamped_report(tmp_path, capsys):
    path = torch_like_checkpoint(tmp_path / "w.pt", payload({}))
    output = tmp_path / "report.json"
    assert check.main(["static", "--weights", str(path), "--output", str(output)]) == 0
    text = output.read_text()
    assert '"created_at"' in text and "+08:00" in text
    assert '"has_one_to_one_branch": false' in text
    assert "one_to_many_nms (no one-to-one branch)" in capsys.readouterr().out


def test_cli_reports_errors_without_a_traceback(tmp_path, capsys):
    assert check.main(["static", "--weights", str(tmp_path / "none.pt")]) == 2
    assert "Weights not found" in capsys.readouterr().err


@pytest.mark.skipif(not WEIGHTS.is_file(), reason="COCO weights missing")
def test_shipped_coco_weights_store_no_head_choice():
    report = check.run_static(WEIGHTS)
    assert report["has_one_to_one_branch"] is True
    assert report["stored_head_choice"] == "absent"


def test_pickle_scan_follows_memoised_keys():
    # The YAML's "end2end" is the literal string; the train_args key reuses it from the
    # pickle memo, so only following the memo finds the training value.
    data = io.BytesIO()
    pickle.Pickler(data, protocol=2).dump(
        [{"end2end": "yaml"}, {"train_args": {"end2end": False}}],
    )
    assert b"end2end" in data.getvalue()
    assert data.getvalue().count(b"end2end") == 1  # the second key is a memo reference
    assert check.scan_pickle(data.getvalue())["train_end2end"] is False


def test_static_scan_reports_clean_errors_for_other_files(tmp_path):
    onnx = tmp_path / "model.onnx"
    onnx.write_bytes(b"\x08\x07\x12\x07pytorch")
    with pytest.raises(check.CheckError, match="not a pickle"):
        check.run_static(onnx)
    legacy = tmp_path / "legacy.pt"
    with open(legacy, "wb") as handle:
        pickle.dump(0x1950A86A20F9469CFC6C, handle, protocol=2)
        pickle.dump({"version": "x"}, handle, protocol=2)
    with pytest.raises(check.CheckError, match="legacy"):
        check.run_static(legacy)
    assert check.main(["static", "--weights", str(onnx)]) == 2
