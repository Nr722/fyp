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
