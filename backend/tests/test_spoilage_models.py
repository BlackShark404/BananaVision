"""RFR artifact contracts using disposable joblib files and synthetic features."""

import copy
import importlib.util
from pathlib import Path

import joblib
import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

from app.services import spoilage

FEATURE_COLUMNS = [
    "cultivar_encoded", "ripeness_encoded", "temperature", "humidity",
    "vpd", "treatment_encoded",
]


@pytest.mark.parametrize("temperature,humidity,expected", [
    (33.6, 70.1, 1.555), (25, 100, 0), (25, 0, 3.168), (0, 50, 0.305),
])
def test_vpd_calculation_kpa_reference_values(temperature, humidity, expected):
    assert spoilage.calc_vpd(temperature, humidity) == expected
METADATA = {
    "feature_columns": FEATURE_COLUMNS,
    "cultivar_map": {0: "Lakatan", 1: "Latundan", 2: "Cardaba"},
    "ripeness_map": {0: "Unripe", 1: "Semi-Ripe", 2: "Ripe", 3: "Overripe"},
    "treatment_map": {0: "Natural", 1: "Ethephon"},
}


class ConstantTree:
    def predict(self, features):
        return np.full(len(features), 9.0)


class RecordingRegressor:
    def __init__(self, feature_count=6):
        self.n_features_in_ = feature_count
        self.estimators_ = [ConstantTree(), ConstantTree()]
        self.seen = []

    def predict(self, features):
        if features.shape[1] != self.n_features_in_:
            raise ValueError("Unexpected feature count")
        self.seen.append(features.copy())
        return np.full(len(features), 9.0)


class TreatmentColumnRegressor:
    n_features_in_ = 6

    def predict(self, features):
        return 14.5 + features[:, 1]


def load_artifact(monkeypatch, tmp_path, artifact):
    path = tmp_path / "spoilage.joblib"
    joblib.dump(artifact, path)
    monkeypatch.setattr(spoilage.settings, "rfr_model_path", str(path))
    predictor = spoilage.SpoilagePredictor()
    predictor.load()
    return predictor


def forbid_fallback(monkeypatch, predictor):
    def unexpected_fallback(*_args, **_kwargs):
        pytest.fail("The loaded estimator must predict instead of using fallback rules")
    monkeypatch.setattr(predictor, "_fallback_predict", unexpected_fallback)


@pytest.mark.parametrize("recorded_vpd", [0, 1.555])
def test_enhanced_prediction_keeps_explicit_vpd_including_zero(
    monkeypatch, tmp_path, recorded_vpd,
):
    predictor = load_artifact(monkeypatch, tmp_path, RecordingRegressor())
    forbid_fallback(monkeypatch, predictor)
    predictor.predict("Lakatan", "Ripe", 22.29, 53.37, vpd=recorded_vpd)
    assert predictor._model.seen[-1][0, 4] == recorded_vpd


def test_saved_training_bundle_uses_embedded_six_feature_forest(monkeypatch, tmp_path):
    features = np.array([[0, 2, 25, 65, 1.1, 0], [1, 1, 28, 70, 1.2, 1]])
    model = RandomForestRegressor(n_estimators=3, random_state=42, n_jobs=1)
    model.fit(features, np.array([9.0, 9.0]))
    predictor = load_artifact(monkeypatch, tmp_path, {"model": model, "metadata": METADATA})
    forbid_fallback(monkeypatch, predictor)

    assert isinstance(predictor._model, RandomForestRegressor)
    assert predictor.uses_enhanced_features
    assert predictor.predict("Lakatan", "Ripe", 25, 65, vpd=1.1) == "9"


def test_bundle_obeys_training_column_order_and_category_encodings(monkeypatch, tmp_path):
    metadata = copy.deepcopy(METADATA)
    metadata["feature_columns"] = [
        "temperature", "treatment_encoded", "humidity", "cultivar_encoded",
        "vpd", "ripeness_encoded",
    ]
    metadata["cultivar_map"] = {2: "Lakatan", 0: "Latundan", 1: "Cardaba"}
    metadata["ripeness_map"] = {0: "Unripe", 3: "Semi-Ripe", 1: "Ripe", 2: "Overripe"}
    metadata["treatment_map"] = {1: "Natural", 0: "Ethephon"}
    predictor = load_artifact(monkeypatch, tmp_path, {
        "model": RecordingRegressor(), "metadata": metadata,
    })
    forbid_fallback(monkeypatch, predictor)

    assert predictor.predict("Lakatan", "Semi Ripe", 29, 72, 1.5, "Ethephon") == "9"
    np.testing.assert_allclose(predictor._model.seen[-1], [[29, 0, 72, 2, 1.5, 3]])


@pytest.mark.parametrize("feature_count", [4, 6])
def test_plain_estimators_keep_legacy_and_enhanced_support(monkeypatch, tmp_path, feature_count):
    predictor = load_artifact(monkeypatch, tmp_path, RecordingRegressor(feature_count))
    forbid_fallback(monkeypatch, predictor)

    assert predictor.predict("Latundan", "Semi Ripe", 28, 70, 1.2, "Ethephon") == "9"
    expected = [[1, 1, 28, 70, 1.2, 1]] if feature_count == 6 else [[1, 1, 28, 70]]
    np.testing.assert_allclose(predictor._model.seen[-1], expected)


def test_plain_estimator_without_feature_metadata_keeps_legacy_support(monkeypatch, tmp_path):
    predictor = load_artifact(monkeypatch, tmp_path, ConstantTree())
    forbid_fallback(monkeypatch, predictor)

    assert not predictor.uses_enhanced_features
    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "9"


def test_estimator_inference_failure_keeps_existing_rule_based_fallback(
    monkeypatch, tmp_path, caplog,
):
    predictor = load_artifact(monkeypatch, tmp_path, RecordingRegressor())

    def failed_predict(_features):
        raise RuntimeError("Synthetic estimator failure")

    monkeypatch.setattr(predictor._model, "predict", failed_predict)

    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "2-4"
    assert "RFR inference error: Synthetic estimator failure" in caplog.text


def test_bundle_computes_vpd_and_uses_training_natural_treatment_default(monkeypatch, tmp_path):
    metadata = copy.deepcopy(METADATA)
    metadata["treatment_map"] = {1: "Natural", 0: "Ethephon"}
    predictor = load_artifact(monkeypatch, tmp_path, {
        "model": RecordingRegressor(), "metadata": metadata,
    })
    forbid_fallback(monkeypatch, predictor)

    assert predictor.predict("Cardaba", "Unripe", 25, 65) == "9"
    np.testing.assert_allclose(
        predictor._model.seen[-1], [[2, 0, 25, 65, spoilage.calc_vpd(25, 65), 1]],
    )


@pytest.mark.parametrize("artifact", [
    {"metadata": METADATA},
    {"model": {}, "metadata": METADATA},
    {"model": RecordingRegressor(5)},
    {"model": RecordingRegressor(), "metadata": "not metadata"},
    {"model": RecordingRegressor(), "metadata": {"feature_columns": FEATURE_COLUMNS[:-1]}},
    {"model": RecordingRegressor(), "metadata": {"feature_columns": ["unknown"] * 6}},
    {"model": RecordingRegressor(), "metadata": {"cultivar_map": {0: "Unknown"}}},
    {"model": RecordingRegressor(), "metadata": {"treatment_map": {0: "Natural"}}},
])
def test_invalid_bundle_uses_existing_fallback_instead_of_wrong_features(
    monkeypatch, tmp_path, artifact, caplog,
):
    predictor = load_artifact(monkeypatch, tmp_path, artifact)

    assert predictor._model is None
    assert "Failed to load RFR model" in caplog.text
    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "2-4"


def test_reload_missing_model_clears_previous_bundle_metadata(monkeypatch, tmp_path):
    predictor = load_artifact(monkeypatch, tmp_path, {
        "model": RecordingRegressor(), "metadata": METADATA,
    })
    assert predictor.uses_enhanced_features
    monkeypatch.setattr(spoilage.settings, "rfr_model_path", str(tmp_path / "missing.joblib"))

    predictor.load()

    assert predictor._model is None
    assert not predictor.is_loaded
    assert not predictor.uses_enhanced_features
    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "2-4"


def test_historical_default_loads_packaged_model_instead_of_short_fallback(
    monkeypatch, tmp_path,
):
    app_dir = tmp_path / "app"
    (app_dir / "services").mkdir(parents=True)
    (app_dir / "ml").mkdir()
    monkeypatch.setattr(spoilage, "__file__", str(app_dir / "services" / "spoilage.py"))
    monkeypatch.setattr(spoilage.settings, "rfr_model_path", "app/ml/weights/spoilage_rfr.joblib")
    monkeypatch.chdir(tmp_path)
    joblib.dump({"model": RecordingRegressor(), "metadata": METADATA},
                app_dir / "ml" / "spoilage_rfr.joblib")

    predictor = spoilage.SpoilagePredictor()
    predictor.load()
    forbid_fallback(monkeypatch, predictor)

    assert predictor.is_loaded and predictor.uses_enhanced_features
    assert predictor.predict("Lakatan", "Unripe", 36.4, 52.6, treatment="Natural") == "9"
    assert predictor._model.seen[-1][0, -1] == 0


@pytest.mark.parametrize("relative", [True, False])
def test_existing_station_artifact_takes_priority_over_packaged_bundle(
    monkeypatch, tmp_path, relative,
):
    app_dir = tmp_path / "app"
    (app_dir / "services").mkdir(parents=True)
    (app_dir / "ml" / "weights").mkdir(parents=True)
    monkeypatch.setattr(spoilage, "__file__", str(app_dir / "services" / "spoilage.py"))
    monkeypatch.chdir(tmp_path)
    station_path = app_dir / "ml" / "weights" / "spoilage_rfr.joblib"
    joblib.dump(RecordingRegressor(4), station_path)
    joblib.dump(RecordingRegressor(6), app_dir / "ml" / "spoilage_rfr.joblib")
    monkeypatch.setattr(spoilage.settings, "rfr_model_path",
                        "app/ml/weights/spoilage_rfr.joblib" if relative else str(station_path))

    predictor = spoilage.SpoilagePredictor()
    predictor.load()

    assert predictor.is_loaded
    assert not predictor.uses_enhanced_features


def test_missing_custom_artifact_does_not_silently_load_packaged_model(monkeypatch, tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "services").mkdir(parents=True)
    (app_dir / "ml").mkdir()
    monkeypatch.setattr(spoilage, "__file__", str(app_dir / "services" / "spoilage.py"))
    joblib.dump(RecordingRegressor(), app_dir / "ml" / "spoilage_rfr.joblib")
    monkeypatch.setattr(spoilage.settings, "rfr_model_path", str(tmp_path / "custom.joblib"))

    predictor = spoilage.SpoilagePredictor()
    predictor.load()

    assert not predictor.is_loaded
    assert predictor._model is None


def test_invalid_artifact_does_not_report_rfr_loaded(monkeypatch, tmp_path):
    predictor = load_artifact(monkeypatch, tmp_path, {"model": {}})
    assert not predictor.is_loaded
    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "2-4"


def test_matrix_audit_uses_runtime_metadata_and_model_mean(monkeypatch, tmp_path, capsys):
    script = Path(__file__).resolve().parents[2] / "test_rfr_matrix.py"
    spec = importlib.util.spec_from_file_location("rfr_matrix_audit", script)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    metadata = copy.deepcopy(METADATA)
    metadata["feature_columns"] = [
        "temperature", "treatment_encoded", "humidity", "cultivar_encoded",
        "vpd", "ripeness_encoded",
    ]
    metadata["treatment_map"] = {1: "Natural", 0: "Ethephon"}
    path = tmp_path / "audit.joblib"
    joblib.dump({"model": TreatmentColumnRegressor(), "metadata": metadata}, path)
    monkeypatch.setattr(audit, "MODEL_PATH", path)
    monkeypatch.chdir(tmp_path)

    audit.run_matrix_test()

    output = capsys.readouterr().out
    natural = [line for line in output.splitlines() if "Natural" in line]
    ethephon = [line for line in output.splitlines() if "Ethephon" in line]
    assert len(natural) == len(ethephon) == 60
    assert all(line.endswith("15.5 days") for line in natural)
    assert all(line.endswith("14.5 days") for line in ethephon)
    assert "Matrix ref" in output and "Station" in output
    assert "results are model means" in output


@pytest.mark.parametrize("point", [0, 1, 1.9999, 2, 2.00001, 5.123456789012345, 0.0000001])
def test_predict_returns_model_number_in_existing_spoilage_field(monkeypatch, tmp_path, point):
    predictor = load_artifact(monkeypatch, tmp_path, RecordingRegressor())
    monkeypatch.setattr(predictor._model, "predict", lambda _: np.array([point]))
    result = predictor.predict("Lakatan", "Ripe", 25, 65)
    assert float(result) == point
    assert len(result) <= 20
    assert "e" not in result.lower()  # Existing DB scalar parser accepts decimal notation.


@pytest.mark.parametrize("point", [float("nan"), float("inf"), -1])
def test_invalid_model_number_uses_existing_fallback(monkeypatch, tmp_path, point):
    predictor = load_artifact(monkeypatch, tmp_path, RecordingRegressor())
    monkeypatch.setattr(predictor._model, "predict", lambda _: np.array([point]))
    assert predictor.predict("Lakatan", "Ripe", 25, 65) == "2-4"
