import sys
import os
import pytest
from xml.dom.minidom import Document

# Add the backend directory to sys.path to resolve imports cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from diplomacy import Game
from viz import apply_webdip_default_borders, generate_current_svg, RichRenderer


def _make_order_layer_document():
    doc = Document()
    svg = doc.createElement('svg')
    doc.appendChild(svg)

    order_layer = doc.createElement('g')
    order_layer.setAttribute('id', 'OrderLayer')
    svg.appendChild(order_layer)

    layer1 = doc.createElement('g')
    layer1.setAttribute('id', 'Layer1')
    order_layer.appendChild(layer1)

    return doc, layer1

def test_apply_webdip_default_borders():
    """
    Tests that the helper correctly assigns historical WebDiplomacy 
    influence boundaries to empty/non-supply center territories.
    """
    game = Game()
    apply_webdip_default_borders(game)
    
    # Check GERMANY's influence
    germany = game.get_power('GERMANY')
    assert 'RUH' in germany.influence
    assert 'PRU' in germany.influence
    assert 'SIL' in germany.influence
    
    # Check ENGLAND's influence
    england = game.get_power('ENGLAND')
    assert 'WAL' in england.influence
    assert 'YOR' in england.influence
    
    # Ensure it doesn't accidentally assign to the wrong power
    assert 'BUR' not in germany.influence
    france = game.get_power('FRANCE')
    assert 'BUR' in france.influence

def test_rich_renderer_get_order_status():
    """
    Tests the logic that correctly maps the parsed order resolution 
    (like 'bounce' or 'void') to the specific unit at the source location.
    """
    game = Game()
    
    # Given the standard S1901M setup, France has an Army in PAR. 
    # Let's mock the adjudication data reporting a bounce.
    mock_adjudication = {
        'FRANCE': {
            'A PAR': ['bounce']
        }
    }
    
    renderer = RichRenderer(game, adjudication_data=mock_adjudication)
    
    # _get_order_status should find "A PAR" and lookup its string in the dictionary
    status = renderer._get_order_status('PAR', 'FRANCE')
    assert 'bounce' in status
    
    # A unit that didn't bounce should return empty
    status_mar = renderer._get_order_status('MAR', 'FRANCE')
    assert status_mar == []


def test_rich_renderer_failed_move_styling():
    game = Game()
    doc, layer1 = _make_order_layer_document()

    bounce_renderer = RichRenderer(
        game,
        adjudication_data={'FRANCE': {'A PAR': ['bounce']}},
    )
    bounce_renderer._issue_move_order(doc, 'PAR', 'BUR', 'FRANCE')
    bounce_arrow = [
        node for node in layer1.getElementsByTagName('line')
        if node.getAttribute('class') == 'varwidthorder'
    ][0]
    assert bounce_arrow.getAttribute('stroke') == '#800000'
    assert bounce_arrow.getAttribute('stroke-dasharray') == '10,5'

    doc, layer1 = _make_order_layer_document()
    void_renderer = RichRenderer(
        game,
        adjudication_data={'FRANCE': {'A PAR': ['void']}},
    )
    void_renderer._issue_move_order(doc, 'PAR', 'BUR', 'FRANCE')
    void_arrow = [
        node for node in layer1.getElementsByTagName('line')
        if node.getAttribute('class') == 'varwidthorder'
    ][0]
    assert void_arrow.getAttribute('stroke') == '#800000'
    assert not void_arrow.hasAttribute('opacity')

def test_generate_current_svg(tmp_path):
    """
    Tests the full execution pipeline of SVG map generation. 
    Uses pytest's built-in tmp_path fixture to generate files securely.
    """
    game = Game()
    
    # tmp_path creates a unique temporary directory for this test invocation
    out_file = tmp_path / "map_test.svg"
    
    # Run the generator
    result_path = generate_current_svg(game, str(out_file))
    
    # Verify the file was created and returned
    assert result_path == str(out_file)
    assert os.path.exists(result_path)
    
    # Verify the contents look like a rendered XML map
    with open(result_path, 'r') as f:
        content = f.read()
        assert "<svg" in content
        assert "S1901M" in content # Check that the game initialized phase rendered


def test_generate_history_svg_for_phase_marks_bounce_maroon(tmp_path):
    from viz import generate_history_svg_for_phase

    game = Game()
    game.clear_units()
    game.set_units('ITALY', 'A VEN')
    game.set_units('AUSTRIA', 'A VIE')
    game.set_orders('ITALY', 'A VEN - TYR')
    game.set_orders('AUSTRIA', 'A VIE - TYR')
    game.process()

    out_file = tmp_path / "history_test.svg"
    result_path = generate_history_svg_for_phase(game, 'S1901M', str(out_file))

    assert result_path == str(out_file)
    assert os.path.exists(result_path)

    with open(result_path, 'r') as f:
        content = f.read()
        assert '#800000' in content
        assert 'stroke-dasharray="10,5"' in content
