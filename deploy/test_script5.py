from diplomacy import Game
import sys
sys.path.append("/home/neil/fyp/deploy/backend")
from viz import RichRenderer

game = Game()
game.set_orders("FRANCE", ["A PAR - GAS"])
game.process()
game.process()
game.set_orders("FRANCE", ["A GAS - SPA"])
game.process()
game.process()

print("Phase is:", game.get_current_phase())
r = RichRenderer(game)
r.render(output_path="test_map_rich.svg")

