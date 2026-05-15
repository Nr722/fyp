# Tactical Scorer

The Tactical Scorer (`tactial_scorer.py`) is a static heuristic evaluator designed to rank possible orders for units on a Diplomacy board based on the current game state.

It operates by generating all possible valid orders for each unit of a given power and assigning a score to each order based on a set of tactical rules. The scorer then returns the top 5 highest-scoring orders for each unit.

### Base Scoring
Every order starts with a base score of 10.

### 1. MOVE Orders
- **Attacking Supply Centers (SCs):** 
  - +100 points for moving into an unowned or enemy Supply Center.
  - An additional +50 points if the SC is currently occupied by an enemy unit.
- **Attacking Enemy Units:** +50 points for attacking an enemy unit on a non-SC space.
- **Friendly Fire Penalty:** -80 points for moving into a space already occupied by one of your own units (self-bouncing).
- **Unsupported Attacks:** -60 points for attacking an occupied enemy space with 0 potential support from friendly units (suicide attacks).
- **Supported Attacks:** +30 points for every friendly unit adjacent to the target that could potentially support the attack.
- **Aggressive Positioning:** +20 points for moving adjacent to an enemy unit.
- **Strategic Value:** +20 points for every unowned or enemy SC adjacent to the target destination.

### 2. SUPPORT Orders
- **Supporting Attacks on SCs:** +100 points for supporting an attack on an unowned or enemy SC.
- **Supporting Attacks on Enemies:** +90 points for supporting an attack on an enemy unit.
- **Defensive Support:** +30 points for supporting a friendly unit defensively or holding ground.

### 3. HOLD Orders
- **Defending SCs:** +40 points for holding a supply center you already own.
- **Holding Front Lines:** +50 points for holding a space that is adjacent to enemy units.

### 4. CONVOY Orders
- **Convoy to SCs:** +150 points for convoying an army to an unowned/enemy SC (with an additional +50 points if occupied by an enemy).
- **Convoy to Attack Enemies:** +100 points for convoying an army to attack an enemy unit.
- **General Repositioning:** +50 points for utilizing water to reposition units.

By applying these heuristics, the bot can rapidly eliminate obviously poor moves (like unsupported attacks or self-bounces) and prioritize aggressive, coordinated actions that capture centers and leverage support mechanics.

### Heuristic Scoring Summary

| Priority | Action | Type | Points |
| :--- | :--- | :--- | :--- |
| 1 | Convoy army to unowned/enemy SC | CONVOY | +150 |
| 2 | Attack/Support attack on unowned/enemy SC | MOVE/SUPPORT | +100 |
| 3 | Convoy army to attack enemy unit | CONVOY | +100 |
| 4 | Support attack on enemy unit | SUPPORT | +90 |
| 5 | Attack enemy unit (non-SC) | MOVE | +50 |
| 6 | Bonus: Target SC is occupied by enemy | MOVE/CONVOY | +50 |
| 7 | Hold front line (adjacent to enemy) | HOLD | +50 |
| 8 | Repositioning via water | CONVOY | +50 |
| 9 | Defend currently owned SC | HOLD | +40 |
| 10 | Supported attack bonus (per friendly unit) | MOVE | +30 |
| 11 | Defensive / Hold support | SUPPORT | +30 |
| 12 | Aggressive positioning (adjacent to enemy) | MOVE | +20 |
| 13 | Strategic space (per adjacent unowned SC) | MOVE | +20 |
| 14 | Base score | ALL | +10 |
| 15 | Boring / Empty space move | MOVE | +5 |
| 16 | **Penalty:** Unsupported attack (1v1) | MOVE | -60 |
| 17 | **Penalty:** Self-bounce / Occied space | MOVE | -80 |

## Move Validation and Auto-Retry

To ensure the AI bot issues coherent and strictly valid orders without logical contradictions, the system employs a Move Validator acting as a self-correction loop during turn generation:

1. **Initial Generation**: The LLM outputs a set of proposed orders for all its units based on the tactical scorer and board state.
2. **Consistency Check**: The system extracts the proposed order strings and calls `check_internal_consistency()` to analyze them for logical flaws (e.g., severe coordination errors like self-bounces, invalid support mechanics, or contradictory commands).
3. **Auto-Retry Loop**: If consistency errors are detected, the system does *not* accept the moves immediately. Instead:
   - The initial, flawed response is appended to the LLM's chat history to preserve context.
   - A `HumanMessage` is inserted with a specific warning detailing the errors: `"Your proposed orders have severe coordination errors. Fix these before submitting: [List of specific consistency errors]"`.
   - The model is then re-prompted to regenerate its turn, taking the exact errors into account to correct its mistakes.
4. **Resolution**: The bot is given up to 3 attempts (a simple retry loop) to finalize an error-free set of orders. If it succeeds, the orders are validated and submitted. If it fails after all retries, the system falls back to guaranteeing at least a basic parsed valid order per location.