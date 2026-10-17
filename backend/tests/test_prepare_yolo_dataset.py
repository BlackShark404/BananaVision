"""Synthetic exports verify grouped copies without model or station access."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.prepare_yolo_dataset import (
    CULTIVARS,
    EXPECTED_NAMES,
    KNOWN_BAD_ROWS,
    PreparationError,
    infer_capture,
    infer_prefix,
    prepare_dataset,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_yolo_dataset.py"


def add_photo(source, split, stem, rows):
    image = source / split / "images" / f"{stem}.jpg"
    label = source / split / "labels" / f"{stem}.txt"
    image.write_bytes(b"synthetic image fixture: " + stem.encode())
    label.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return image, label


@pytest.fixture
def export(tmp_path):
    def create(*, groups=3, batches=("B1",)):
        source = tmp_path / "source"
        for split in ("train", "valid", "test"):
            (source / split / "images").mkdir(parents=True)
            (source / split / "labels").mkdir()
        (source / "data.yaml").write_text(
            f"train: ../train/images\nval: ../valid/images\ntest: ../test/images\n"
            f"nc: 12\nnames: {json.dumps(EXPECTED_NAMES)}\n",
            encoding="utf-8",
        )
        for cultivar_index, cultivar in enumerate(CULTIVARS):
            for ordinal in range(1, groups + 1):
                for batch in batches:
                    prefix = f"{batch}_{cultivar.title()}{ordinal}_NoneChemical"
                    for stage in range(4):
                        cls = cultivar_index * 4 + stage
                        for split, camera, variants in (
                            ("train", "top-1-", 2),
                            ("valid", "left", 1),
                            ("test", "back", 1),
                        ):
                            for variant in range(variants):
                                stem = (
                                    f"{prefix}_{100 + stage:05d}_{camera}_jpg.rf.{split}{variant}"
                                )
                                add_photo(source, split, stem, [f"{cls} 0.5 0.5 0.2 0.4"])
        return source

    return create


def snapshot(source):
    return {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("camera", ["top", "left-1-", "right-2", "back", "rear-1-"])
def test_filename_grouping_preserves_bunch_prefix_across_capture_and_camera(camera):
    name = f"B2_Latundan3_CH_01131_{camera}_jpg.rf.augmented.jpg"
    assert infer_prefix(name) == "B2_Latundan3_CH"
    assert infer_capture(name) == "B2_Latundan3_CH_01131"


def test_grouped_copy_is_reproducible_complete_and_preserves_source(export, tmp_path):
    source = export()
    before = snapshot(source)
    first = prepare_dataset(source, tmp_path / "prepared", seed=19)
    second = prepare_dataset(source, tmp_path / "repeated", seed=19)
    assert snapshot(source) == before
    assert first["group_assignments"] == second["group_assignments"]
    assert first["summary"] == second["summary"]
    assert first["files"] == second["files"]
    assert len(first["group_assignments"]) == 9
    assert "unverified" in first["grouping_assumption"]
    assert "export convention" in first["heldout_policy"]
    observed_groups = {}
    for item in first["files"]:
        observed_groups.setdefault(item["group"], set()).add(item["assigned_split"])
        assert (tmp_path / "prepared" / item["image"]).read_bytes() == (
            source / item["source_image"]
        ).read_bytes()
        assert (tmp_path / "prepared" / item["label"]).read_bytes() == (
            source / item["source_label"]
        ).read_bytes()
        if item["assigned_split"] != "train":
            assert item["original_split"] in {"valid", "test"}
    assert all(len(splits) == 1 for splits in observed_groups.values())
    assert first["exclusions"]
    assert all(item["original_split"] == "train" for item in first["exclusions"])
    for split, summary in first["summary"].items():
        assert summary["groups"] == 3
        assert set(summary["class_boxes"]) == set(EXPECTED_NAMES)
        assert all(count > 0 for count in summary["class_boxes"].values())
        assert summary["images"] > 0, split
    yaml = (tmp_path / "prepared" / "data.yaml").read_text()
    assert f'path: "{(tmp_path / "prepared").as_posix()}"' in yaml
    assert "../" not in yaml
    assert json.loads((tmp_path / "prepared" / "manifest.json").read_text()) == first


def test_aliases_join_batches_without_claiming_verified_identity(export, tmp_path):
    source = export(batches=("B1", "B2"))
    aliases = {
        f"{batch}_{cultivar.title()}{ordinal}_NoneChemical": f"{cultivar}_{ordinal}"
        for batch in ("B1", "B2")
        for cultivar in CULTIVARS
        for ordinal in (1, 2, 3)
    }
    manifest = prepare_dataset(source, tmp_path / "prepared", aliases=aliases)
    assert len(manifest["group_assignments"]) == 9
    assert manifest["aliases"] == aliases
    assert all(item["group"] == aliases[item["inferred_prefix"]] for item in manifest["files"])


def test_only_confirmed_exact_background_rows_are_removed_and_logged(export, tmp_path):
    source = export()
    baseline = prepare_dataset(source, tmp_path / "baseline")
    target_group = next(
        group
        for group, split in baseline["group_assignments"].items()
        if "Latundan" in group and split == "train"
    )
    rows = [f"{cls} 0.5 0.5 0.2 0.4" for cls in (8, 9, 9, 9, 10, 11)]
    for name, bad_row in KNOWN_BAD_ROWS.items():
        add_photo(source, "train", Path(name).stem, [*rows, bad_row])
    lookalike = "B4_Latundan1_NoneChemical_02570_top_jpg.rf.unconfirmed"
    add_photo(source, "train", lookalike, [*rows, "10 0.5 0.5 0.85 1"])
    before = snapshot(source)
    manifest = prepare_dataset(
        source,
        tmp_path / "prepared",
        aliases={
            "B4_Latundan1_NoneChemical": target_group,
        },
    )
    assert snapshot(source) == before
    assert len(manifest["corrections"]) == 2
    for correction in manifest["corrections"]:
        assert correction["line"] == 7 and correction["applied_to_copy"] is True
        assert Path(correction["source_label"]).name in KNOWN_BAD_ROWS
        output_label = (
            tmp_path
            / "prepared"
            / "train"
            / "labels"
            / f"train__{Path(correction['source_label']).name}"
        )
        assert output_label.read_text().splitlines() == rows
    untouched = tmp_path / "prepared" / "train" / "labels" / f"train__{lookalike}.txt"
    assert len(untouched.read_text().splitlines()) == 7


def test_changed_known_defect_requires_review_instead_of_deleting_other_row(export, tmp_path):
    source = export()
    name = next(iter(KNOWN_BAD_ROWS))
    add_photo(source, "train", Path(name).stem, ["10 0.5 0.5 0.2 0.4"] * 7)
    with pytest.raises(PreparationError, match="Known defect changed"):
        prepare_dataset(source, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


def test_explicit_capture_quarantine_precedes_mixed_cultivar_validation(export, tmp_path):
    source = export()
    prefix, capture = "B1_Latundan1_NoneChemical", "09999"
    for camera in ("top-1-", "left", "right"):
        for variant in (0, 1):
            add_photo(
                source,
                "train",
                f"{prefix}_{capture}_{camera}_jpg.rf.bad{variant}",
                ["5 0.5 0.5 0.2 0.4"],
            )
    add_photo(source, "test", f"{prefix}_{capture}_back_jpg.rf.bad", ["5 0.5 0.5 0.2 0.4"])
    before = snapshot(source)
    with pytest.raises(PreparationError, match="mixed cultivar"):
        prepare_dataset(source, tmp_path / "blocked")
    reason = "Filename and cultivar labels disagree; needs human review"
    manifest = prepare_dataset(
        source,
        tmp_path / "prepared",
        exclude_captures={
            f"{prefix}_{capture}": reason,
        },
    )
    assert snapshot(source) == before
    quarantined = [
        item for item in manifest["exclusions"] if item["reason"] == "explicit_capture_quarantine"
    ]
    assert len(quarantined) == 7
    assert all(
        item["capture"] == f"{prefix}_{capture}" and item["explanation"] == reason
        for item in quarantined
    )
    assert not any(item["capture"] == f"{prefix}_{capture}" for item in manifest["files"])


@pytest.mark.parametrize(
    "bad_row",
    [
        "12 .5 .5 .2 .4",
        "0 nan .5 .2 .4",
        "0 .5 .5 0 .4",
        "0 .5 .5 1.1 .4",
        "0 .5 .5 .2",
        "0.5 .5 .5 .2 .4",
    ],
)
def test_invalid_rows_fail_before_creating_output(export, tmp_path, bad_row):
    source = export()
    label = next((source / "train" / "labels").glob("*.txt"))
    label.write_text(bad_row)
    with pytest.raises(PreparationError, match="Invalid label"):
        prepare_dataset(source, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


def test_class_coverage_failure_reports_heldout_eligibility(export, tmp_path):
    source = export()
    for split in ("valid", "test"):
        for label in (source / split / "labels").glob("*.txt"):
            if label.read_text().startswith("11 "):
                label.write_text("10 0.5 0.5 0.2 0.4\n")
    with pytest.raises(PreparationError, match="latundan_unripe: 3 total groups, 0"):
        prepare_dataset(source, tmp_path / "prepared")
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("destination", ["same", "nested", "ancestor", "existing"])
def test_path_guards_never_overwrite_or_place_output_in_source(export, tmp_path, destination):
    source = export()
    output = {
        "same": source,
        "nested": source / "new-copy",
        "ancestor": tmp_path,
        "existing": tmp_path / "existing",
    }[destination]
    if destination == "existing":
        output.mkdir()
        (output / "keep.txt").write_text("user data")
    before = snapshot(source)
    with pytest.raises(PreparationError, match="already exists|disjoint"):
        prepare_dataset(source, output)
    assert snapshot(source) == before
    if destination == "existing":
        assert (output / "keep.txt").read_text() == "user data"


def test_unknown_alias_and_quarantine_keys_fail_usefully(export, tmp_path):
    source = export()
    with pytest.raises(PreparationError, match="Alias keys"):
        prepare_dataset(source, tmp_path / "bad-alias", aliases={"typo": "group"})
    with pytest.raises(PreparationError, match="Quarantine keys"):
        prepare_dataset(source, tmp_path / "bad-quarantine", exclude_captures={"typo": "review"})


def test_cli_reads_alias_and_quarantine_json_without_app_or_model_dependencies(export, tmp_path):
    source = export()
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"B1_Latundan1_NoneChemical": "latundan_1"}))
    capture = "B1_Latundan1_NoneChemical_09999"
    add_photo(source, "train", f"{capture}_top-1-_jpg.rf.suspect", ["5 .5 .5 .2 .4"])
    quarantine = tmp_path / "exclude-captures.json"
    quarantine.write_text(json.dumps({capture: "Cultivar disagreement; pending human review"}))
    before = snapshot(source)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--source",
            str(source),
            "--output",
            str(tmp_path / "prepared"),
            "--seed",
            "123",
            "--aliases",
            str(aliases),
            "--exclude-captures",
            str(quarantine),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["output"] == str(tmp_path / "prepared")
    manifest = json.loads((tmp_path / "prepared" / "manifest.json").read_text())
    assert manifest["aliases"] == {"B1_Latundan1_NoneChemical": "latundan_1"}
    assert "latundan_1" in manifest["group_assignments"]
    quarantined = [
        item for item in manifest["exclusions"] if item["reason"] == "explicit_capture_quarantine"
    ]
    assert len(quarantined) == 1
    assert quarantined[0]["capture"] == capture
    assert snapshot(source) == before
