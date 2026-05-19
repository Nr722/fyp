import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from function_tools.tactial_scorer import score_individual_orders

class MockMap:
    def __init__(self):
        self.scs = ['PAR', 'BER', 'MUN', 'KIE', 'VIE', 'LON', 'BEL']
    
    def abut_list(self, loc):
        # Extremely simplified adjacency for testing
        adj = {
            'PAR': ['BUR', 'PIC'],
            'BUR': ['PAR', 'MUN'],
            'MUN': ['BUR', 'BER', 'KIE'],
            'LON': ['ENG'],
            'ENG': ['LON', 'BEL'],
            'BEL': ['ENG', 'BUR']
        }
        return adj.get(loc, [])

class MockGame:
    def __init__(self):
        self.map = MockMap()
        self.possible_orders = {}
        self.orderable_locs = []
        self.units = {}
        self.centers = {}

    def get_all_possible_orders(self):
        return self.possible_orders

    def get_orderable_locations(self, power):
        return self.orderable_locs

    def get_units(self, power=None):
        if power:
            return self.units.get(power, [])
        return self.units
        
    def get_centers(self, power):
        return self.centers.get(power, [])


def test_friendly_fire_penalty():
    # Setup game where France has units in PAR and BUR, and one tries to move to the other
    game = MockGame()
    game.orderable_locs = ["PAR"]
    game.units = {"FRANCE": ["A PAR", "A BUR"], "GERMANY": ["A MUN"]}
    game.centers = {"FRANCE": ["PAR"]}
    game.possible_orders = {"PAR": ["A PAR - BUR"]}
    
    scores = score_individual_orders(game, "FRANCE")
    
    # Base(10) - FriendlyFire(80) + adj_bonus? -> Very negative
    assert len(scores["PAR"]) == 1
    move_score = scores["PAR"][0]["score"]
    assert move_score < 0
    assert scores["PAR"][0]["order"] == "A PAR - BUR"


def test_unsupported_suicide_attack_penalty():
    # Setup game where France attacks occupied MUN (Germany) with no support
    game = MockGame()
    game.orderable_locs = ["BUR"]
    game.units = {"FRANCE": ["A BUR"], "GERMANY": ["A MUN"]} # BUR is adjacent to MUN
    game.centers = {"FRANCE": ["PAR"], "GERMANY": ["MUN"]}
    game.possible_orders = {"BUR": ["A BUR - MUN"]}
    
    scores = score_individual_orders(game, "FRANCE")
    
    # Base(10) + AttackEnemyCenter(100) + AttackEnemyUnit(50) - Unsupported(60)
    # Plus tactical bonuses:
    # - adjacent to enemy? Yes (MUN borders enemies because BUR is there... wait, let's see)
    # It adds adjacency bonuses in the heuristic.
    move_score = scores["BUR"][0]["score"]
    assert move_score == 140
    # Should still be positive because SCs are valuable, but notably penalized by 60


def test_supported_attack_bonus():
    # Setup game where France attacks occupied MUN (Germany) WITH potential support from another unit (e.g., KIE or BER, let's say we have A KIE)
    game = MockGame()
    game.orderable_locs = ["BUR"]
    game.units = {"FRANCE": ["A BUR", "A KIE"], "GERMANY": ["A MUN"]}
    game.centers = {"FRANCE": ["PAR"], "GERMANY": ["MUN"]}
    game.possible_orders = {"BUR": ["A BUR - MUN"]}
    
    scores = score_individual_orders(game, "FRANCE")
    
    # We have a unit in KIE which abuts MUN.
    # Base(10) + AttackEnemyCenter(100) + AttackEnemyUnit(50) + FriendlySupport(1x30) = 190
    move_score = scores["BUR"][0]["score"]
    assert move_score >= 190


def test_convoy_bonus():
    # Setup game where England sets up a convoy
    game = MockGame()
    game.orderable_locs = ["ENG"]
    game.units = {"ENGLAND": ["F ENG", "A LON"], "FRANCE": ["A BEL"]}
    game.centers = {"ENGLAND": ["LON"], "FRANCE": ["BEL"]}
    game.possible_orders = {"ENG": ["F ENG C A LON - BEL"]}
    
    scores = score_individual_orders(game, "ENGLAND")
    
    # AttackEnemyCenter via Convoy(150 + 50) + Base(10) = 210
    move_score = scores["ENG"][0]["score"]
    assert move_score == 210
