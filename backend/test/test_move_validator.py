import pytest
import sys
import os

# Add the backend directory to sys.path so we can import function_tools
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from function_tools.move_validator import check_internal_consistency

def test_valid_independent_moves():
    """Test standard moves with no conflicts."""
    orders = [
        "A PAR - BUR",
        "A MAR - SPA",
        "F BRE H"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 0

def test_self_bounce_error():
    """Test two units ordered to the same destination without support."""
    orders = [
        "A PAR - BUR",
        "A MAR - BUR"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 1
    assert "Self-bounce error" in errors[0]
    assert "BUR" in errors[0]

def test_valid_supported_move():
    """Test a correctly supported move."""
    orders = [
        "A PAR S A MAR - BUR",
        "A MAR - BUR"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 0

def test_support_move_mismatch():
    """Test a unit providing support for a move, but the target unit does something else."""
    orders = [
        "A PAR S A MAR - BUR",
        "A MAR - SPA"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 1
    assert "Coordination mismatch" in errors[0]
    assert "supports a move, but the target unit is actually doing:" in errors[0]

def test_valid_supported_hold():
    """Test a correctly supported hold."""
    orders = [
        "A PAR S A MAR",
        "A MAR H"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 0

def test_support_hold_mismatch():
    """Test a unit supporting a hold, while the target unit decides to move."""
    orders = [
        "A PAR S A MAR",
        "A MAR - BUR"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 1
    assert "Coordination mismatch" in errors[0]
    assert "supports a hold/non-move, but the target unit is moving" in errors[0]

def test_valid_convoy():
    """Test a correct convoy setup honoring the VIA syntax."""
    orders = [
        "F ENG C A LON - BRE",
        "A LON - BRE VIA"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 0

def test_convoy_mismatch():
    """Test a fleet attempting a convoy while the army goes elsewhere."""
    orders = [
        "F ENG C A LON - BRE",
        "A LON - EDI"
    ]
    errors = check_internal_consistency(orders)
    assert len(errors) == 1
    assert "Coordination mismatch" in errors[0]
    assert "attempts to convoy, but the target army is doing" in errors[0]

def test_hallucinated_location_in_move():
    """
    FAULT INJECTION: Test system resilience against non-existent board locations.
    LLM hallucinates a location 'XYZ' that doesn't exist on the board.
    """
    orders = [
        "A PAR - XYZ",  # XYZ is not a valid location
        "F BRE H"
    ]
    errors = check_internal_consistency(orders)
    # The validator should catch or gracefully handle this
    # (It may not error immediately, but should not crash)
    assert isinstance(errors, list)

def test_hallucinated_support_destination():
    """
    FAULT INJECTION: Test support order with non-existent destination.
    """
    orders = [
        "A PAR S A MAR - XYZ",  # XYZ doesn't exist
        "A MAR - XYZ"
    ]
    errors = check_internal_consistency(orders)
    # Should handle gracefully
    assert isinstance(errors, list)

def test_malformed_order_missing_unit_type():
    """
    FAULT INJECTION: Test order missing unit type prefix (A or F).
    This would come from Pydantic validation failure in LLM output.
    """
    orders = [
        "PAR - BUR",  # Missing unit type prefix
        "F BRE H"
    ]
    errors = check_internal_consistency(orders)
    # Should not crash, may produce error or skip malformed order
    assert isinstance(errors, list)

def test_malformed_order_empty_string():
    """
    FAULT INJECTION: Test empty order string.
    """
    orders = [
        "",  # Empty string
        "A PAR - BUR"
    ]
    errors = check_internal_consistency(orders)
    # Should handle gracefully
    assert isinstance(errors, list)

def test_malformed_order_broken_syntax():
    """
    FAULT INJECTION: Test syntactically broken order.
    """
    orders = [
        "A PAR - - BUR",  # Double dash
        "F BRE H"
    ]
    errors = check_internal_consistency(orders)
    # Should not crash
    assert isinstance(errors, list)

def test_hallucinated_convoy_location():
    """
    FAULT INJECTION: Test convoy with non-existent fleet location.
    """
    orders = [
        "F INVALID C A LON - BRE",  # INVALID is not a real location
        "A LON - BRE VIA"
    ]
    errors = check_internal_consistency(orders)
    # Should gracefully handle
    assert isinstance(errors, list)
