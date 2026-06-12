import json
import os
import sys
from diplomacy import Game

sys.path.append(os.getcwd())
from function_tools.tactical_scorer import score_individual_orders

COASTS = ('/SC', '/NC', '/EC', '/WC')

def norm(o):
    """Whitespace + case normalisation."""
    return ' '.join(str(o).upper().split())

def strip_coasts(o):
    """Coast-insensitive form, for diagnosing format-only misses."""
    toks = [t[:-3] if t.endswith(COASTS) else t for t in norm(o).split()]
    return ' '.join(toks)

def legal_orders_for_loc(possible_all, loc3):
    """All legal orders for a 3-letter province, across any coast key."""
    out = []
    for k, v in possible_all.items():
        if k[:3].upper() == loc3:
            out.extend(v)
    return out

def backtest_scorer(file_path, debug_misses=False):
    with open(file_path, 'r') as f:
        game_data = json.load(f)

    phases = game_data.get('phases', [])
    evaluated = 0            # orders the scorer had an opinion on (true denominator)
    excluded_no_loc = 0      # orders whose location wasn't in scored_options
    top1 = top5 = 0          # strict (normalised) matches
    top1_loose = top5_loose = 0   # coast-insensitive matches
    rand1_sum = rand5_sum = 0.0   # expected hits for a random pick / random 5

    print(f"\n--- Backtesting on {os.path.basename(file_path)} ---")

    for phase_data in phases:
        phase_name = phase_data.get('name')
        if not phase_name or not phase_name.endswith('M'):
            continue  # movement phases only

        game = Game()
        state = phase_data.get('state', {})
        for power, units in state.get('units', {}).items():
            game.set_units(power, units)
        for power, centers in state.get('centers', {}).items():
            game.set_centers(power, centers)

        possible_all = game.get_all_possible_orders()
        actual_orders = phase_data.get('orders', {})

        for power, orders in actual_orders.items():
            if not orders:
                continue
            scored_options = score_individual_orders(game, power)

            for actual_order in orders:
                parts = actual_order.split()
                if len(parts) < 2:
                    continue
                loc = parts[1][:3].upper()

                if loc not in scored_options:
                    excluded_no_loc += 1
                    continue

                suggested = [s['order'] for s in scored_options[loc]]  # top 5
                evaluated += 1

                # --- strict (normalised) match ---
                a = norm(actual_order)
                sug = [norm(s) for s in suggested]
                if a in sug:
                    top5 += 1
                    if sug and a == sug[0]:
                        top1 += 1
                else:
                    # --- coast-insensitive fallback (diagnostic) ---
                    al = strip_coasts(actual_order)
                    sugl = [strip_coasts(s) for s in suggested]
                    if al in sugl:
                        top5_loose += 1
                        if sugl and al == sugl[0]:
                            top1_loose += 1
                    elif debug_misses:
                        print(f"  MISS {phase_name} {power}: '{actual_order}' "
                              f"not in {suggested}")

                # --- random baseline for this unit ---
                n_legal = len(legal_orders_for_loc(possible_all, loc))
                if n_legal > 0:
                    rand1_sum += 1 / n_legal
                    rand5_sum += min(5, n_legal) / n_legal

    return dict(evaluated=evaluated, excluded_no_loc=excluded_no_loc,
                top1=top1, top5=top5,
                top1_loose=top1_loose, top5_loose=top5_loose,
                rand1_sum=rand1_sum, rand5_sum=rand5_sum)

if __name__ == "__main__":
    print("Starting backtest of tactical scorer...")
    game_files = [
        'test/game_433761_ENGLAND_AG.json',
        'test/game_433967_ENGLAND_IT.json',
    ]

    agg = dict(evaluated=0, excluded_no_loc=0, top1=0, top5=0,
               top1_loose=0, top5_loose=0, rand1_sum=0.0, rand5_sum=0.0)

    for gf in game_files:
        if os.path.exists(gf):
            r = backtest_scorer(gf, debug_misses=False)
            for k in agg:
                agg[k] += r[k]
        else:
            print(f"  (missing file: {gf})")

    n = agg['evaluated']
    if n:
        # strict numbers
        s_top1 = agg['top1'] / n * 100
        s_top5 = agg['top5'] / n * 100
        # strict + coast-insensitive (upper bound if format is the only issue)
        l_top1 = (agg['top1'] + agg['top1_loose']) / n * 100
        l_top5 = (agg['top5'] + agg['top5_loose']) / n * 100
        # random baselines
        r_top1 = agg['rand1_sum'] / n * 100
        r_top5 = agg['rand5_sum'] / n * 100

        print("\n--- GLOBAL RESULTS ---")
        print(f"Orders evaluated (scorer had options): {n}")
        print(f"Orders excluded (loc not scored):      {agg['excluded_no_loc']}")
        print(f"\nStrict match    Top-1: {s_top1:5.2f}%   Top-5: {s_top5:5.2f}%")
        print(f"Coast-insens.   Top-1: {l_top1:5.2f}%   Top-5: {l_top5:5.2f}%")
        print(f"Random baseline Top-1: {r_top1:5.2f}%   Top-5: {r_top5:5.2f}%")
        if l_top5 - s_top5 > 1:
            print("\nNote: gap between strict and coast-insensitive means some "
                  "'misses' are format (coast) differences, not strategy.")