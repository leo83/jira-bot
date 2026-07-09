"""Tests for ComponentService (static fallback + fuzzy matching)."""

from app.component_service import ComponentService
from app.components import components


def test_static_fallback_when_no_jira():
    svc = ComponentService()
    available = svc.get_available_components()
    assert available == components
    # Returned list must be a copy, not the module-level list
    available.append("x")
    assert svc.get_available_components() == components


def test_exact_match_from_static_list():
    svc = ComponentService()
    selected, message = svc.find_component("component-a")
    assert selected == "component-a"
    assert message == ""


def test_fuzzy_match_close_typo():
    svc = ComponentService()
    # "component-aa" is close enough to "component-a"
    selected, message = svc.find_component("component-aa")
    assert selected == "component-a"
    assert message == ""


def test_no_match_returns_default_and_message():
    svc = ComponentService()
    selected, message = svc.find_component("totally-unrelated-xyz")
    assert selected == "default"
    assert "No close match" in message
    assert "Available components" in message


def test_cyrillic_input_does_not_crash():
    # Transliteration path must not raise even if nothing matches the latin list
    svc = ComponentService()
    selected, message = svc.find_component("авиа-параметры")
    assert selected == "default"
    assert message  # a non-empty message with the available components
