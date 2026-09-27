"""Certified shared-odd-cycle equality before the frozen low-name strategy.

Two nonadjacent regions adjacent to every vertex of an odd NEQ cycle must
have the same name in a four-name palette. Certificates use only original real
contacts. Equality is logical: no face identity or mother-line geometry merges.
The existing conditional propagation and selection code is reused unchanged.
"""

from copy import deepcopy

from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_odd_cycle_eq import learn_odd_cycle_equalities

POLICY = 'quaternary-low-color-odd-cycle-eq-v1'


def solve_odd_cycle_eq(document, *, geometry=None, decision_limit=128, probe_limit=512):
    """Add certified raw-graph equalities once, then keep guarded low-name choice.

    There is no recursive learning from inferred edges, oracle query, choice
    rescue, or rollback of committed colors. All learning evidence and the
    unchanged underlying run are returned for a posterior independent audit.
    Inputs with external candidate states or EQ are outside this version.
    """
    original = deepcopy(document)
    learning = learn_odd_cycle_equalities(original)
    augmented = deepcopy(original)
    if learning['equal_names']:
        augmented['equal_names'] = deepcopy(learning['equal_names'])
    run = solve_low_color(augmented, geometry=geometry, probe=True,
                          decision_limit=decision_limit, probe_limit=probe_limit)
    return {'schema_version': 1, 'policy': POLICY, 'original_input': original,
            'learning': learning, 'augmented_input': augmented, 'run': run,
            'oracle_feedback_to_producer': False, 'old_colors_read': False}
