"""Tests for entity availability code generation."""

from collections.abc import Callable


def test_entity_set_available_action(generate_main: Callable[[str], str]) -> None:
    main_cpp = generate_main(
        "tests/component_tests/esphome/test_entity_availability.yaml"
    )

    assert main_cpp.count("EntitySetAvailableAction<>(test_entity)") == 2
    assert main_cpp.count("->set_available([]() -> bool {") == 2
    assert "return false;" in main_cpp
    assert "return true;" in main_cpp
