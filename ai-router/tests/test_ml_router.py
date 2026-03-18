"""Tests for ai-router/ml_router.py — ML routing classifier."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Skip all tests if torch not available
torch = pytest.importorskip("torch", exc_type=Exception)
np = pytest.importorskip("numpy", exc_type=Exception)


@pytest.fixture(autouse=True)
def temp_model_path(tmp_path):
    """Override MODEL_PATH so tests don't touch real model."""
    import ml_router
    original = ml_router.MODEL_PATH
    ml_router.MODEL_PATH = tmp_path / "test_router.pt"
    # Reset singleton
    ml_router._instance = None
    yield tmp_path / "test_router.pt"
    ml_router.MODEL_PATH = original
    ml_router._instance = None


class TestFeatureExtraction:
    def test_feature_vector_shape(self):
        from ml_router import extract_features
        features = extract_features("hello world")
        assert isinstance(features, np.ndarray)
        assert len(features.shape) == 1
        assert features.shape[0] > 10

    def test_different_queries_different_features(self):
        from ml_router import extract_features
        f1 = extract_features("install firefox")
        f2 = extract_features("write a REST API in Python")
        assert not np.array_equal(f1, f2)

    def test_question_mark_feature(self):
        from ml_router import extract_features
        f_q = extract_features("what is linux?")
        f_no_q = extract_features("what is linux")
        assert f_q[2] == 1.0
        assert f_no_q[2] == 0.0

    def test_action_keywords_detected(self):
        from ml_router import extract_features
        f = extract_features("restart the waybar service")
        assert f[3] == 1.0

    def test_code_keywords_detected(self):
        from ml_router import extract_features
        f = extract_features("write a function to sort arrays")
        assert f[4] == 1.0


class TestSyntheticData:
    def test_generates_data(self):
        from ml_router import generate_synthetic_data
        data = generate_synthetic_data()
        assert len(data) > 100
        routes = set(label for _, label in data)
        assert len(routes) >= 5

    def test_all_routes_represented(self):
        from ml_router import generate_synthetic_data, ROUTE_CLASSES
        data = generate_synthetic_data()
        routes_present = set(label for _, label in data)
        for route in ROUTE_CLASSES:
            assert route in routes_present, f"Missing route in synthetic data: {route}"


class TestMLRouterModel:
    def test_predict_without_training(self):
        from ml_router import MLRouter
        router = MLRouter()
        route, confidence = router.predict("hello")
        assert route is None
        assert confidence == 0.0

    def test_train_and_predict(self):
        from ml_router import MLRouter, generate_synthetic_data
        router = MLRouter()
        data = generate_synthetic_data()
        router.train(data)

        route, confidence = router.predict("what's the weather forecast")
        assert route is not None
        assert 0.0 <= confidence <= 1.0

    def test_model_saves_and_loads(self, temp_model_path):
        from ml_router import MLRouter, generate_synthetic_data
        router1 = MLRouter()
        data = generate_synthetic_data()
        router1.train(data)
        assert temp_model_path.exists()

        router2 = MLRouter()
        route, confidence = router2.predict("install docker")
        assert route is not None

    def test_evaluate(self):
        from ml_router import MLRouter, generate_synthetic_data
        router = MLRouter()
        data = generate_synthetic_data()
        report = router.evaluate(data)
        assert "accuracy" in report
        assert 0.0 <= report["accuracy"] <= 1.0

    def test_route_classes_consistent(self):
        from ml_router import ROUTE_CLASSES
        assert "local" in ROUTE_CLASSES
        assert "sonnet" in ROUTE_CLASSES
        assert "haiku+web" in ROUTE_CLASSES


class TestSingleton:
    def test_get_router_returns_same_instance(self):
        from ml_router import get_router
        r1 = get_router()
        r2 = get_router()
        assert r1 is r2
