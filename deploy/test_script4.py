from diplomacy import Game
from diplomacy.engine.renderer import Renderer

game = Game()
game.set_orders("FRANCE", ["A PAR - GAS"])
game.process()
game.process()
game.set_orders("FRANCE", ["A GAS - SPA"])
game.process()
game.process()

print("Phase is:", game.get_current_phase())
r = Renderer(game)
r.render(output_path="test_map.svg")

