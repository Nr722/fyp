from diplomacy import Game
game = Game()
game.process() # S1901M -> S1901R -> F1901M
game.set_orders("FRANCE", ["A PAR - GAS"])
game.process()
game.process() # S1901R
game.set_orders("FRANCE", ["A GAS - SPA"])
game.process()
print("F1901R phase:", game.get_current_phase())
print("Centers:", game.get_centers("FRANCE"))
print("Influence:", game.get_power("FRANCE").influence)
