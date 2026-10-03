"""Run the frozen saturation closure with an equivalent detector prefilter.

Only the detector implementation changes. Returned versions, certificates,
statistics and nested traces retain the frozen semantic wire format. Optional
``work_log`` telemetry is external to that format so actual optimized work is
not confused with the old detector's retained reference counters.
"""

from copy import deepcopy

from scripts.quaternary_conditional_diamond_contacts import propagate_diamond_contacts
from scripts.quaternary_contact_model import NameState
from scripts.quaternary_triangle_saturation_contacts import MODEL, VERSION
from scripts.quaternary_triangle_saturation_prefilter import find_triangle_saturations_prefilter


IMPLEMENTATION_VERSION = "quaternary-triangle-saturation-prefilter-closure-v1"


def propagate_prefilter_contacts(document, *, work_log=None):
    """Keep the old closure's complete output while pruning detector work.

    The narrow copied loop keeps all old premises and bounded-progress guards.
    EQ and singleton consequences remain local exactly as in the frozen loop.
    Each nonterminal detector call appends its own work row to ``work_log``;
    solved/conflicting diamond outcomes do not invoke or log the detector.
    """
    if work_log is not None and not isinstance(work_log, list):
        raise ValueError("work_log must be a list or None")
    original, work = deepcopy(document), deepcopy(document)
    rounds, removed_candidates = [], []
    n = len(document.get("sides", [])) if isinstance(document, dict) else 0
    while True:
        if len(rounds) > 4 * n:
            raise ValueError("triangle closure did not make bounded progress")
        base = propagate_diamond_contacts(work)
        check = (find_triangle_saturations_prefilter(
            work, base["domains"], base["equal_names"], work_log=work_log)
                 if base["status"] == "underdetermined" else None)
        rounds.append({"document": deepcopy(work), "outcome": deepcopy(base),
                       "triangle_check": check})
        if check is None or not check["certificates"]:
            break
        index = {side: i for i, side in enumerate(work["sides"])}
        seen = set()
        for certificate in check["certificates"]:
            target = certificate["target"]
            removed = certificate["removed_colors"]
            domain = base["domains"][index[target]]
            if (target in seen or not removed or len(removed) != len(set(removed))
                    or any(color not in domain for color in removed)
                    or any([target, color] in removed_candidates for color in removed)):
                raise ValueError("triangle closure did not make bounded progress")
            seen.add(target)
            remaining = [color for color in domain if color not in removed]
            work.setdefault("states", {})[target] = NameState.from_candidates(remaining).to_quaternary()
            removed_candidates.extend([[target, color] for color in removed])
    outcome = deepcopy(rounds[-1]["outcome"])
    outcome["model"] = MODEL
    outcome["original_input"] = original
    outcome["triangle_saturation"] = {"version": VERSION, "rounds": rounds,
                                      "removed_candidates": removed_candidates}
    return outcome
