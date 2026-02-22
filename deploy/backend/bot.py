"""
Bot AI logic for the Diplomacy game.
"""
import random

def _phase_type(game):
    phase = game.get_current_phase() or ''
    return phase[-1] if phase else 'M'

def get_bot_orders(game, bot_name):
    """Generate simple bot orders per phase type.

    - Movement (M): random valid order per unit, default HOLD when needed.
    - Retreats (R): prefer a retreat move; fallback to disband if only that is available.
    - Adjustments (A): prefer BUILD/REMOVE choices; fallback to WAIVE if needed.
    """
    all_orders_dict = game.get_all_possible_orders()
    orderable_locs = game.get_orderable_locations(bot_name)
    orders = []
    phase_t = _phase_type(game)

    if not orderable_locs:
        return orders

    if phase_t == 'M':
        power_units = game.get_units(bot_name)
        for loc in orderable_locs:
            possible = all_orders_dict.get(loc, [])
            if not possible:
                continue
            unit_at_loc = next((u for u in power_units if u.endswith(f" {loc}")), None)
            if unit_at_loc:
                unit_type = unit_at_loc.split()[0].replace('*', '')
                candidates = [o for o in possible if o.startswith(f"{unit_type} {loc}")]
                if candidates:
                    orders.append(random.choice(candidates))
                else:
                    orders.append(f"{unit_type} {loc} H")
        return orders

    if phase_t == 'R':
        # Retreats: options typically include moves and a disband option (e.g., 'D')
        for loc in orderable_locs:
            possible = all_orders_dict.get(loc, [])
            if not possible:
                continue
            # Prefer a retreat move (contains ' - ') over disband (often ends with ' D' or equals 'D')
            moves = [o for o in possible if ' - ' in o]
            if moves:
                orders.append(random.choice(moves))
            else:
                # Fallback: pick any valid option (likely disband)
                orders.append(random.choice(possible))
        return orders

    # Adjustments 'A'
    for loc in orderable_locs:
        possible = all_orders_dict.get(loc, [])
        if not possible:
            continue
        builds = [o for o in possible if o.startswith('BUILD')]
        removes = [o for o in possible if o.startswith('REMOVE')]
        waives = [o for o in possible if o.startswith('WAIVE') or o == 'WAIVE']
        if builds:
            orders.append(random.choice(builds))
        elif removes:
            orders.append(random.choice(removes))
        elif waives:
            orders.append(random.choice(waives))
        else:
            # Unknown/edge options; pick something
            orders.append(random.choice(possible))
    return orders
