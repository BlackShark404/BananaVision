"""Shared test defaults."""

import sys

import pytest


@pytest.fixture(autouse=True)
def colour_check_off_for_placeholder_frames(request, monkeypatch):
    """Classifier geometry tests use blank synthetic frames (np.zeros) as placeholders.

    The colour check reads real pixels and would treat a black frame as dark background, so
    it is off unless the test module sets COLOUR_CHECK = True (see test_colour_check.py).
    Only applies when the test already imported the classifier, so import order is unchanged.
    """
    if getattr(request.module, "COLOUR_CHECK", False):
        return
    classification = sys.modules.get("app.services.classification")
    if classification is None:
        return
    settings = classification.settings
    if hasattr(settings, "model_copy"):
        monkeypatch.setattr(classification, "settings",
                            settings.model_copy(update={"yolo_colour_check": False}))
