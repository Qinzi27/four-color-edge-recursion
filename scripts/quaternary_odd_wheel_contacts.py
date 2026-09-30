"""Add a certified physical odd-wheel conflict after frozen binary closure."""

from copy import deepcopy

from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_odd_wheel import find_odd_wheel


MODEL = "quaternary-odd-wheel-contact-relations-v1"


def propagate_wheel_contacts(document):
    """Keep every binary trace and add a separately checkable conflict proof.

    Only an underdetermined base state is scanned. Domains and relations are
    not edited to fake an empty binary relation when the wheel proves a
    higher-order conflict. Their sound derivation remains the old audit's job.
    """
    base = propagate_logical_contacts(document)
    outcome = deepcopy(base)
    outcome["model"] = MODEL
    outcome["base_status"] = base["status"]
    outcome["wheel_check"] = None
    if base["status"] == "underdetermined":
        outcome["wheel_check"] = find_odd_wheel(document, base["domains"])
        if outcome["wheel_check"]["certificate"] is not None:
            outcome["status"] = "conflict"
            outcome["colors"] = None
    return outcome
