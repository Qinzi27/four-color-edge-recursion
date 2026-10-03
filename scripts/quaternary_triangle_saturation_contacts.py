"""Iterate physical triangle saturation using local, auditable unary deletions."""

from copy import deepcopy

from scripts.quaternary_conditional_diamond_contacts import propagate_diamond_contacts
from scripts.quaternary_contact_model import NameState
from scripts.quaternary_triangle_saturation import find_triangle_saturations


MODEL = "quaternary-triangle-saturation-contact-relations-v1"
VERSION = "quaternary-triangle-saturation-closure-v1"


def propagate_saturation_contacts(document):
    """Alternate the frozen diamond closure and proved local domain deletions.

    Each next round keeps the same physical lines, anchors and supplied EQ/NEQ.
    Inner conditional EQs are recomputed by diamond closure, never promoted to
    the next round's root premises. New singleton words are unanchored. Every
    nested round is retained; the top-level trace remains the final base trace
    and therefore is not a measure of the whole operation's work.
    """
    original, work = deepcopy(document), deepcopy(document)
    rounds, removed_candidates = [], []
    n = len(document.get("sides", [])) if isinstance(document, dict) else 0
    while True:
        if len(rounds) > 4 * n:
            raise ValueError("triangle closure did not make bounded progress")
        base = propagate_diamond_contacts(work)
        check = (find_triangle_saturations(work, base["domains"], base["equal_names"])
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
