from diplomacy.engine.renderer import Renderer
from diplomacy import Game
import os

class RichRenderer(Renderer):
    def __init__(self, game, adjudication_data=None, **kwargs):
        super().__init__(game, **kwargs)
        self.adjudication_data = adjudication_data or {}

    def _set_influence(self, xml_map, loc, power_name, has_supply_center=False):
        # Override influence to only color based on game JSON "centers"
        # If it's pure influence (has_supply_center=False), we ignore it so it doesn't prematurely color map
        if not has_supply_center:
            return xml_map
        return super()._set_influence(xml_map, loc, power_name, has_supply_center)

    def _get_order_status(self, src_loc, power_name):
        if not self.adjudication_data:
            return []
        
        # Find unit at src_loc
        # The game object should be in the state where orders were issued (pre-resolution)
        units = self.game.get_units(power_name)
        target_unit = None
        for u in units:
            # u is like "A PAR" or "F STP/SC"
            parts = u.split()
            if len(parts) < 2: continue
            loc = parts[1]
            if loc == src_loc:
                target_unit = u
                break
            # Handle coasts
            if '/' in loc and loc.split('/')[0] == src_loc:
                target_unit = u
                break
        
        if target_unit:
            power_results = self.adjudication_data.get(power_name, {})
            # results is a list like ['bounce']
            return power_results.get(target_unit, [])
        return []

    def _issue_move_order(self, xml_map, src_loc, dest_loc, power_name):
        # We reimplement this to add styling based on status
        
        # Checking if dislodged unit (move from retreat phase?)
        is_dislodged = self.game.get_current_phase()[-1] == 'R'
        src_loc_x, src_loc_y = self._get_unit_center(src_loc, is_dislodged)
        dest_loc_x, dest_loc_y = self._get_unit_center(dest_loc, is_dislodged)
        
        # Calculation for arrow position
        delta_x = dest_loc_x - src_loc_x
        delta_y = dest_loc_y - src_loc_y
        vector_length = (delta_x ** 2 + delta_y ** 2) ** 0.5
        
        if vector_length == 0:
            return xml_map

        # Getting symbol size safely (assuming Army default or similar)
        # In Renderer, self.metadata['symbol_size'] is keyed by type usually 'Army'/'Fleet'
        # We can just pick one size as approximation or try to find unit type.
        # But standard renderer uses 'Army' size for delta calculation logic mostly.
        # Checking source code: delta_dec = float(self.metadata['symbol_size'][ARMY][1]) / 2 ...
        
        try:
            delta_dec = float(self.metadata['symbol_size']['Army'][1]) / 2 + 2 * self._colored_stroke_width()
        except:
            delta_dec = 10 # Fallback

        dest_loc_x_adj = str(round(src_loc_x + (vector_length - delta_dec) / vector_length * delta_x, 2))
        dest_loc_y_adj = str(round(src_loc_y + (vector_length - delta_dec) / vector_length * delta_y, 2))

        src_s = str(src_loc_x)
        src_y_s = str(src_loc_y)
        dest_x_s = str(dest_loc_x_adj)
        dest_y_s = str(dest_loc_y_adj)

        g_node = xml_map.createElement('g')

        # Shadow
        line_with_shadow = xml_map.createElement('line')
        line_with_shadow.setAttribute('x1', src_s)
        line_with_shadow.setAttribute('y1', src_y_s)
        line_with_shadow.setAttribute('x2', dest_x_s)
        line_with_shadow.setAttribute('y2', dest_y_s)
        line_with_shadow.setAttribute('class', 'varwidthshadow')
        line_with_shadow.setAttribute('stroke-width', str(self._plain_stroke_width()))

        # Check status
        status = self._get_order_status(src_loc, power_name)
        status_str = str(status) # list to string
        is_bounce = 'bounce' in status_str
        is_void = 'void' in status_str

        # Arrow
        line_with_arrow = xml_map.createElement('line')
        line_with_arrow.setAttribute('x1', src_s)
        line_with_arrow.setAttribute('y1', src_y_s)
        line_with_arrow.setAttribute('x2', dest_x_s)
        line_with_arrow.setAttribute('y2', dest_y_s)
        line_with_arrow.setAttribute('class', 'varwidthorder')
        line_with_arrow.setAttribute('stroke', self.metadata['color'][power_name])
        line_with_arrow.setAttribute('stroke-width', str(self._colored_stroke_width()))
        line_with_arrow.setAttribute('marker-end', 'url(#arrow)')

        if is_bounce:
            line_with_arrow.setAttribute('stroke-dasharray', '10,5')
        
        if is_void:
            line_with_arrow.setAttribute('opacity', '0.3')

        g_node.appendChild(line_with_shadow)
        g_node.appendChild(line_with_arrow)
        
        self._append_to_layer(xml_map, g_node, 'OrderLayer')
        return xml_map
    
    def _append_to_layer(self, xml_map, node, layer_id):
        def _attr(node_element, attr_name):
            return node_element.attributes[attr_name].value

        for child_node in xml_map.getElementsByTagName('svg')[0].childNodes:
            if child_node.nodeName == 'g' and _attr(child_node, 'id') == layer_id:
                for layer_node in child_node.childNodes:
                    if layer_node.nodeName == 'g' and _attr(layer_node, 'id') == 'Layer1':
                        layer_node.appendChild(node)
                        return

def generate_history_svg(game, output_path):
    """
    Generates an SVG for the PREVIOUS phase, including results of orders.
    """
    history = list(game.get_phase_history())
    if not history:
        return None

    last_phase_data = history[-1]
    
    # Create a dummy game to render
    temp_game = Game(map_name=game.map_name)
    temp_game.set_phase_data(last_phase_data)
    
    # Get status from the passed game (which has processed the turn)
    status = game.get_order_status()
    
    renderer = RichRenderer(temp_game, adjudication_data=status)
    renderer.render(incl_orders=True, incl_abbrev=True, output_path=output_path)
    
    return output_path
