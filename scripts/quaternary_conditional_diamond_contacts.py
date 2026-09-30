"""Close conditional diamond equalities without exporting phase assumptions."""

from copy import deepcopy

from scripts.quaternary_conditional_diamond import find_conditional_diamonds
from scripts.quaternary_odd_wheel_contacts import propagate_wheel_contacts


MODEL = "quaternary-conditional-diamond-contact-relations-v1"
VERSION = "quaternary-conditional-diamond-closure-v1"


def propagate_diamond_contacts(document):
    """Alternate frozen wheel closure and certified local equality batches.

    The input document, states and anchors are never edited. A learned EQ is
    appended only to this call's local document; later decision-loop calls
    start from their own original premises. Every intermediate frozen wheel
    outcome and exact local document is saved for separate audit. Top-level
    trace fields remain the last round's literal trace; consumers must count
    all round traces explicitly rather than mistaking this for total work.
    """
    original, work = deepcopy(document), deepcopy(document)
    rounds, equalities = [], []
    n = len(document.get("sides", [])) if isinstance(document, dict) else 0
    limit = n * (n - 1) // 2
    while True:
        base = propagate_wheel_contacts(work)
        check = (find_conditional_diamonds(work, base["domains"], base["relations"])
                 if base["status"] == "underdetermined" else None)
        rounds.append({"document": deepcopy(work), "outcome": deepcopy(base),
                       "diamond_check": check})
        if check is None or not check["certificates"]:
            break
        existing = {frozenset(pair) for pair in work.get("equal_names", [])}
        for certificate in check["certificates"]:
            pair = deepcopy(certificate["pair"])
            key = frozenset(pair)
            # An explicit EQ already leaves no off-diagonal matrix entries.
            # A repeated result therefore signals an internal contract error.
            if key in existing or len(equalities) >= limit:
                raise ValueError("conditional equality closure did not make bounded progress")
            existing.add(key)
            work.setdefault("equal_names", []).append(deepcopy(pair))
            equalities.append(pair)
    outcome = deepcopy(rounds[-1]["outcome"])
    outcome["model"] = MODEL
    outcome["original_input"] = original
    outcome["conditional_eq"] = {"version": VERSION, "rounds": rounds,
                                 "equal_names": equalities}
    return outcome
