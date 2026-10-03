"""Audit the additive triangle-saturation guarded producer.

The event, exact-oracle and schedule checks retain the frozen odd-wheel
contract. Each contact audit independently replays every diamond and wheel round
and verifies each complete physical quotient-triangle deletion batch. Raw oracle inputs
remain original physical separator edges, initial anchors and actual choices;
conditional EQ and saturation premises never enter the oracle. Saved replay performs
no producer execution, detector call, propagation or exact-oracle search.
"""

from collections import Counter
from copy import deepcopy
from itertools import product
from math import prod
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_geometry import audit_geometry, _same, _mask, _pairs
from scripts.audit_quaternary_low_color import _preserved, _selection
from scripts.audit_quaternary_logical_neq import verify_logical_inequalities
from scripts.check_quaternary_triangle_saturation import audit_saturation_contacts
from scripts.audit_quaternary_order_probe import _edges
from scripts.scan_low_color_obstruction_states import digest, persistent_phases, raw_graph
from scripts.validate_structural_restart import audit_refutation
from scripts.validate_quaternary_contacts_v2 import check_domains, check_matrix, check_state
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_odd_cycle_eq import verify_odd_cycle_equalities
from scripts.validate_quaternary_contacts_v2 import expected_state, raw_metadata, require

AUDIT_VERSION = "quaternary-low-color-triangle-saturation-audit-v1"
POLICY = "quaternary-low-color-triangle-saturation-v1"


def _preserved_all_rounds(outcome, assignments):
    """Preserve raw solutions through every outer and nested saved outcome.

    In particular, the final projection is insufficient: every intermediate
    wheel closure, diamond closure and outer saturation closure must retain
    the same raw witness/enumeration under the phase's actual assumptions.
    """
    for outer in outcome['triangle_saturation']['rounds']:
        diamond = outer['outcome']
        for inner in diamond['conditional_eq']['rounds']:
            _preserved(inner['outcome'], assignments)
        _preserved(diamond, assignments)
    _preserved(outcome, assignments)


def _bind_envelope(document, envelope):
    """Verify every learned premise before inspecting producer or oracle evidence."""
    require('different_names' not in document and not document.get("states") and not document.get("equal_names"),
            "odd-cycle-EQ audit requires original NEQ and anchors only; states/EQ unsupported")
    require(type(envelope["schema_version"]) is int and envelope["schema_version"] == 1
            and envelope["policy"] == POLICY, "wrong odd-cycle-EQ envelope schema")
    require(envelope["oracle_feedback_to_producer"] is False
            and envelope["old_colors_read"] is False, "invalid odd-cycle-EQ production mode")
    _same(envelope["original_input"], document, "odd-cycle-EQ original raw input")
    require(isinstance(envelope['learning'], dict)
            and set(envelope['learning']) == {'equalities', 'inequalities'}, 'combined learning fields differ')
    verified = verify_odd_cycle_equalities(document, envelope["learning"]["equalities"])
    neq_verified = verify_logical_inequalities(document, envelope['learning']['inequalities'])
    require(verified["passed"] is True, "odd-cycle-EQ certificate verification failed")
    augmented = deepcopy(document)
    if envelope["learning"]["equalities"]["equal_names"]:
        augmented["equal_names"] = deepcopy(envelope["learning"]["equalities"]["equal_names"])
    if envelope['learning']['inequalities']['different_names']:
        augmented['different_names'] = deepcopy(envelope['learning']['inequalities']['different_names'])
    _same(envelope["augmented_input"], augmented, "odd-cycle-EQ augmented input")
    result = envelope["run"]
    _same(result["original_input"], augmented, "odd-cycle-EQ producer input")
    require(result["probe"] is True, "odd-cycle-EQ requires guarded propagation")
    return augmented, result, verified, neq_verified


def audit_triangle_saturation(document, envelope, *, geometry=None, adapted=None,
                    assignment_limit=262144, node_limit=200000):
    """Return independently verified evidence, including unsafe choices as data.

    ``passed`` concerns evidence/trace integrity; ``commitment_counts.unsafe``
    separately counts SAT-to-UNSAT commitments. UNKNOWN never counts as safe.
    Exact certificates are deduplicated in ``oracle_records`` and referenced by
    indices. The first unsafe commitment additionally contains full evidence.
    """
    require(type(assignment_limit) is int and assignment_limit >= 0, "invalid assignment limit")
    require(type(node_limit) is int and node_limit >= 0, "invalid oracle node limit")
    augmented, result, equality_check, inequality_check = _bind_envelope(document, envelope)
    # Raw domains contain only original singleton anchors, never learned EQ.
    sides, initial_domains, _ = raw_metadata(document)
    require((geometry is None) == (adapted is None), "geometry and adapted must be supplied together")
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line["left"]], index[line["right"]])))
                    for line in document["lines"] if line["kind"] == "separator"})
    geometry_check, context = None, None
    if geometry is not None:
        _same(adapted["contact_document"], document, "adapter contact input")
        geometry_check, actual_edges = audit_geometry(geometry, adapted)
        require(edges == actual_edges, "geometry audit and raw edges disagree")
        model = build_whole_lines(geometry)
        require(sides == ["S" + str(i) for i in range(len(model.plane_map.faces))],
                "geometric schedule requires global ordered side IDs")
        context = model, current_segments(model), level_metadata(model)
    _same(result["original_input"], augmented, "low-color augmented input")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1
            and result["policy"] == "quaternary-low-color-triangle-saturation-conditional-v1", "wrong producer schema")
    require(result["schedule"] == ("mother-peer-with-frame-only-fallback-v1" if context else
            "first-unresolved-input-order-v1"), "incorrect schedule label")
    require(type(result["probe"]) is bool and type(result["backtracks"]) is int
            and result["backtracks"] == 0 and result["oracle_feedback_to_producer"] is False
            and result["old_colors_read"] is False, "invalid production mode")
    for name in ("decision_limit", "probe_limit"):
        require(type(result[name]) is int and result[name] >= 0, "invalid production resource limit")
    phases, events = result["phases"], result["events"]
    require(isinstance(phases, list) and bool(phases) and isinstance(events, list), "missing phases/events")
    require(phases[0]["kind"] == "main", "initial phase must be persistent")
    _same(phases[0]["document"], augmented, "initial augmented propagation document")
    phase_audits = [audit_saturation_contacts(phase["document"], phase["outcome"]) for phase in phases]
    size = prod(len(values) for values in initial_domains)
    enumerate_all = size <= assignment_limit
    legal = ([values for values in product(*initial_domains)
              if all(values[a] != values[b] for a, b in edges)] if enumerate_all else None)
    legal_count = len(legal) if enumerate_all else None
    phase_checks, preserved_count = 0, 0
    oracle_records, oracle_cache = [], {}

    def raw_oracle(fixed):
        """Cache ONLY raw graph plus actual commitment signatures, not phase domains."""
        key = tuple(sorted(fixed.items()))
        if key not in oracle_cache:
            evidence = solve_exact(len(sides), edges, fixed, node_limit=node_limit)
            verified = verify_exact_result(len(sides), edges, fixed, evidence)
            oracle_cache[key] = len(oracle_records)
            oracle_records.append({"input": {"n": len(sides), "edges": [list(p) for p in edges],
                                            "anchors": [list(p) for p in key]},
                                   "result": evidence, "verification": verified})
        return oracle_cache[key]

    def check_phase(phase_number, current_legal, oracle_index):
        """Use exhaustive raw solutions and, separately, a raw oracle witness."""
        nonlocal phase_checks, preserved_count
        outcome = phases[phase_number]["outcome"]
        evidence = oracle_records[oracle_index]["result"]
        if enumerate_all:
            _preserved_all_rounds(outcome, current_legal)
            phase_checks += 1
            preserved_count += len(current_legal)
            if evidence["status"] != "unknown":
                require(bool(current_legal) == (evidence["status"] == "sat"),
                        "complete enumeration and raw oracle disagree")
        if evidence["status"] == "sat":
            _preserved_all_rounds(outcome, [evidence["witness"]])

    committed = {index[side]: color for side, color in document.get("anchors", {}).items()}
    initial_oracle = raw_oracle(committed)
    check_phase(0, legal, initial_oracle)
    current_phase, consumed = 0, 1
    choices, probes, rejections = 0, 0, 0
    commitment_counts = {"safe": 0, "unsafe": 0, "unknown": 0, "preexisting_unsat": 0}
    rejection_counts = {"exact_unsat": 0, "unknown": 0}
    steps, first_bad = [], None
    for event_number, event in enumerate(events):
        require(choices < result["decision_limit"], "event after decision limit")
        before_phase = current_phase
        before = phases[before_phase]["outcome"]
        require(before["status"] == "underdetermined", "event after terminal propagation status")
        require(type(event["before_phase"]) is int and event["before_phase"] == before_phase,
                "event does not continue latest persistent phase")
        side, symbol = event["side"], event["symbol"]
        require(side in index and type(symbol) is int, "invalid selected identity or literal")
        selected, expected_selection = _selection(sides, before["domains"], context)
        require(index[side] == selected, "side violates declared schedule")
        candidates = before["domains"][selected]
        require(symbol == min(candidates) and len(candidates) > 1, "choice is not minimum unresolved color")
        _same(event["candidates_before"], candidates, "event candidates")
        selection = event["selection"]
        require(selection["side"] == selected and selection["side_id"] == side,
                "selection identity mismatch")
        _same(selection["candidate_order"], candidates, "selection low-color order")
        expected_selection.update(side_id=side, candidate_order=candidates)
        _same(selection, expected_selection, "scheduler metadata")
        before_oracle = raw_oracle(committed)
        trial_fixed = {**committed, selected: symbol}
        trial_oracle = raw_oracle(trial_fixed)
        trial_legal = [values for values in legal if values[selected] == symbol] if enumerate_all else None
        trial_document = deepcopy(phases[before_phase]["document"])
        trial_document.setdefault("anchors", {})[side] = symbol
        if result["probe"]:
            require(probes < result["probe_limit"], "trial after probe limit")
            require(type(event["trial_phase"]) is int and event["trial_phase"] == consumed,
                    "trial phase omitted, reused, or out of order")
            require(consumed < len(phases) and phases[consumed]["kind"] == "trial", "wrong trial phase kind")
            _same(phases[consumed]["document"], trial_document, "trial assumptions")
            check_phase(consumed, trial_legal, trial_oracle)
            trial_phase = consumed
            consumed += 1
            probes += 1
        else:
            require(event["trial_phase"] is None, "unprobed event has trial")
            trial_phase = None
        kind = event["kind"]
        require(kind in ("reject", "commit"), "unsupported event")
        if kind == "reject":
            require(result["probe"] and phases[trial_phase]["outcome"]["status"] == "conflict",
                    "candidate rejection lacks a proved propagation conflict")
            require(event["extension_claim"] == "refuted", "rejection claim mismatch")
            require(not trial_legal if enumerate_all else True, "rejection removed a raw legal coloring")
            status = oracle_records[trial_oracle]["result"]["status"]
            require(status != "sat", "rejected trial has a complete raw witness")
            rejection_counts["exact_unsat" if status == "unsat" else "unknown"] += 1
            rejections += 1
            after_document = deepcopy(phases[before_phase]["document"])
            remaining = [color for color in candidates if color != symbol]
            after_document.setdefault("states", {})[side] = expected_state(remaining, False)["quaternary"]
            require(consumed < len(phases) and phases[consumed]["kind"] == "main", "missing post-rejection main")
            _same(phases[consumed]["document"], after_document, "post-rejection restrictions")
            current_phase = consumed
            consumed += 1
            after_oracle = before_oracle
            check_phase(current_phase, legal, after_oracle)
            extension = "refuted"
        else:
            choices += 1
            if result["probe"]:
                require(phases[trial_phase]["outcome"]["status"] != "conflict", "conflicting trial was committed")
                current_phase = trial_phase
            else:
                require(consumed < len(phases) and phases[consumed]["kind"] == "main", "missing committed phase")
                _same(phases[consumed]["document"], trial_document, "commitment assumptions")
                current_phase = consumed
                consumed += 1
                check_phase(current_phase, trial_legal, trial_oracle)
            claim = (("complete-witness" if phases[current_phase]["outcome"]["status"] == "solved"
                     else "inconclusive") if result["probe"] else "unchecked")
            require(event["extension_claim"] == claim, "commitment overstates extension evidence")
            committed, legal = trial_fixed, trial_legal
            after_oracle = trial_oracle
            before_status = oracle_records[before_oracle]["result"]["status"]
            after_status = oracle_records[after_oracle]["result"]["status"]
            extension = ("preexisting_unsat" if before_status == "unsat" else
                         "unknown" if "unknown" in (before_status, after_status) else
                         "unsafe" if after_status == "unsat" else "safe")
            commitment_counts[extension] += 1
        require(type(event["after_phase"]) is int and event["after_phase"] == current_phase,
                "wrong post-event phase index")
        step = {"event_index": event_number, "kind": kind, "side": side, "symbol": symbol,
                "before_phase": before_phase, "trial_phase": trial_phase, "after_phase": current_phase,
                "before_oracle_index": before_oracle, "trial_oracle_index": trial_oracle,
                "after_oracle_index": after_oracle,
                "before_status": oracle_records[before_oracle]["result"]["status"],
                "after_status": oracle_records[after_oracle]["result"]["status"],
                "extendibility": extension}
        steps.append(step)
        if extension == "unsafe" and first_bad is None:
            first_bad = {**step, "event": deepcopy(event),
                         "before": deepcopy(oracle_records[before_oracle]),
                         "after": deepcopy(oracle_records[after_oracle])}
    require(consumed == len(phases), "unreferenced propagation phases")
    require(type(result["final_phase"]) is int and result["final_phase"] == current_phase, "wrong final phase")
    final = phases[current_phase]["outcome"]
    require(all(type(result[name]) is int for name in ("choices", "probes", "rejections"))
            and result["choices"] == choices and result["probes"] == probes and result["rejections"] == rejections,
            "incorrect event telemetry")
    for name in ("name_states", "domains", "colors"):
        _same(result[name], final[name], "final " + name)
    if final["status"] == "underdetermined":
        require(choices == result["decision_limit"] or (result["probe"] and probes == result["probe_limit"]),
                "unexplained early stop")
        require(result["status"] == "incomplete" and result["reason"] ==
                ("decision-limit-exhausted" if choices == result["decision_limit"]
                 else "probe-limit-exhausted"), "budget exhaustion mislabeled")
    else:
        require(result["status"] == final["status"], "terminal status mismatch")
        require(result["reason"] == ("complete-coloring-verified" if final["status"] == "solved"
                else "propagation-conflict-under-current-commitments"), "terminal reason mismatch")
    if final["colors"] is not None:
        values = [final["colors"][side] for side in sides]
        require(all(values[i] in initial_domains[i] for i in range(len(sides)))
                and all(values[a] != values[b] for a, b in edges), "final colors violate raw constraints")
    return {"passed": True, "audit_version": AUDIT_VERSION, "geometry": geometry_check,
            "odd_cycle_eq_check": equality_check,
            "logical_neq_check": inequality_check,
            "phase_count": len(phases), "phase_audits": phase_audits,
            "trace_steps_checked": sum(row["trace_steps_checked"] for row in phase_audits),
            "initial_oracle_index": initial_oracle, "oracle_records": oracle_records, "steps": steps,
            "first_bad_commitment": first_bad, "commitment_counts": commitment_counts,
            "rejection_counts": rejection_counts,
            "oracle_unknown": sum(row["result"]["status"] == "unknown" for row in oracle_records),
            "full_enumeration": {"status": "run" if enumerate_all else "not_run",
                "reason": None if enumerate_all else "initial_assignment_product_exceeds_limit",
                "assignment_product": size, "assignment_limit": assignment_limit,
                "literal_assignments_checked": size if enumerate_all else 0,
                "initial_legal_assignments": legal_count, "phase_checks": phase_checks,
                "legal_assignments_preserved": preserved_count},
            "oracle_scope": "original_real_neq_initial_anchors_and_actual_commitments_only",
            "oracle_feedback_to_producer": False,
            "schedule_audit": "shared_mother_peer_selector_with_explicit_frame_fallback" if context
                              else "independent_first_unresolved_input_order",
            "scope": "Passed audits can contain unsafe commitments; unknown is not safe or UNSAT."}


def _replay_raw_preservation(document, result, audit, resources):
    """Recompute raw enumeration and verify witnesses against every saved phase.

    A committed trial and its persistent phase have the same phase index. The
    mapping below checks each allocated phase exactly once; rejected trials
    keep their proposed anchor, but their following persistent phase does not.
    Neither the legal assignments nor the oracle inputs contain learned EQ.
    """
    sides, domains, _ = raw_metadata(document)
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    size = prod(len(values) for values in domains)
    enumerate_all = size <= resources['assignment_limit']
    initial_legal = ([values for values in product(*domains)
                      if all(values[a] != values[b] for a, b in edges)]
                     if enumerate_all else None)
    committed = {index[side]: color for side, color in document.get('anchors', {}).items()}
    phase_inputs = {0: (deepcopy(committed), audit['initial_oracle_index'])}

    def bind(phase, fixed, oracle_index):
        """Repeated references must have precisely the same actual promises."""
        value = (deepcopy(fixed), oracle_index)
        if phase in phase_inputs:
            _same(phase_inputs[phase], value, 'saved phase raw promises differ')
        phase_inputs[phase] = value

    for event, step in zip(result['events'], audit['steps']):
        bind(event['before_phase'], committed, step['before_oracle_index'])
        trial = {**committed, index[event['side']]: event['symbol']}
        bind(event['trial_phase'], trial, step['trial_oracle_index'])
        if event['kind'] == 'commit':
            committed = trial
        bind(event['after_phase'], committed, step['after_oracle_index'])
    require(set(phase_inputs) == set(range(len(result['phases']))),
            'raw preservation phase coverage differs')
    preserved_count = 0
    for phase_number, (fixed, oracle_index) in sorted(phase_inputs.items()):
        outcome = result['phases'][phase_number]['outcome']
        oracle = audit['oracle_records'][oracle_index]['result']
        if enumerate_all:
            legal = [values for values in initial_legal
                     if all(values[side] == color for side, color in fixed.items())]
            _preserved_all_rounds(outcome, legal)
            preserved_count += len(legal)
            if oracle['status'] != 'unknown':
                require(bool(legal) == (oracle['status'] == 'sat'),
                        'saved raw enumeration and oracle disagree')
        if oracle['status'] == 'sat':
            _preserved_all_rounds(outcome, [oracle['witness']])
    expected = {'status': 'run' if enumerate_all else 'not_run',
                'reason': None if enumerate_all else 'initial_assignment_product_exceeds_limit',
                'assignment_product': size, 'assignment_limit': resources['assignment_limit'],
                'literal_assignments_checked': size if enumerate_all else 0,
                'initial_legal_assignments': len(initial_legal) if enumerate_all else None,
                'phase_checks': len(result['phases']) if enumerate_all else 0,
                'legal_assignments_preserved': preserved_count}
    _same(audit['full_enumeration'], expected, 'saved raw enumeration differs')
    final = result['phases'][result['final_phase']]['outcome']
    if final['colors'] is not None:
        values = [final['colors'][side] for side in sides]
        require(all(values[i] in domains[i] for i in range(len(sides)))
                and all(values[a] != values[b] for a, b in edges),
                'saved final colors violate original raw constraints')


def check_triangle_saturation_artifacts(document, envelope, audit, resources, *, geometry=None, adapted=None):
    """Verify every exact certificate against raw NEQ and actual commitments."""
    for name in ("decision_limit", "probe_limit", "assignment_limit", "node_limit"):
        require(type(resources[name]) is int and resources[name] >= 0, "invalid saved resource limit")
    augmented, result, equality_check, inequality_check = _bind_envelope(document, envelope)
    require(isinstance(result['phases'], list) and bool(result['phases'])
            and result['phases'][0]['kind'] == 'main',
            'saved initial phase must be persistent main')
    require(audit["audit_version"] == AUDIT_VERSION, "saved audit version differs")
    _same(audit["odd_cycle_eq_check"], equality_check, "saved odd-cycle-EQ verification differs")
    _same(audit['logical_neq_check'], inequality_check, 'saved logical-NEQ verification differs')
    require((geometry is None) == (adapted is None), "geometry and adapted must be supplied together")
    geometry_check = None
    if geometry is not None:
        _same(adapted["contact_document"], document, "saved raw adapter input")
        geometry_check, _ = audit_geometry(geometry, adapted)
    _same(audit["geometry"], geometry_check, "saved geometry audit differs")
    require(audit["oracle_scope"] == "original_real_neq_initial_anchors_and_actual_commitments_only",
            "saved exact scope differs")
    expected_schedule = ("shared_mother_peer_selector_with_explicit_frame_fallback" if geometry is not None
                         else "independent_first_unresolved_input_order")
    require(audit["schedule_audit"] == expected_schedule, "saved audit schedule differs")
    check_saved_schedule(augmented, result, geometry, resources)
    require(audit['passed'] is True and audit['oracle_feedback_to_producer'] is False,
            'independent audit contract differs')
    require(not document.get('states') and not document.get('equal_names'),
            'exact raw audit requires original NEQ and singleton anchors')
    require(result['decision_limit'] == resources['decision_limit']
            and result['probe_limit'] == resources['probe_limit'], 'producer limits differ')
    sides = document['sides']
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    phase_count = check_transitions(augmented, result, audit['phase_audits'])
    require(audit['phase_count'] == phase_count and audit['trace_steps_checked'] == sum(
        p['trace_steps_checked'] for p in audit['phase_audits']), 'trace counters differ')
    records, used, statuses, signatures = audit['oracle_records'], set(), Counter(), set()
    for record in records:
        raw = record['input']
        require(set(raw) == {"n", "edges", "anchors"}, "extra oracle input premises")
        require(type(raw['n']) is int, "oracle vertex count is not an integer")
        _same(raw['edges'], [list(edge) for edge in edges], 'oracle graph differs')
        require(raw['n'] == len(sides), 'oracle vertex coverage differs')
        fixed = dict(raw['anchors'])
        _same(raw['anchors'], [list(p) for p in sorted(fixed.items())], 'noncanonical oracle commitments')
        signature = tuple(sorted(fixed.items()))
        require(signature not in signatures, 'duplicated oracle signature')
        signatures.add(signature)
        require(record['result']['node_limit'] == resources['node_limit'], 'oracle budget differs')
        verified = verify_exact_result(len(sides), edges, fixed, record['result'])
        require(verified['passed'], 'exact certificate rejected')
        _same(verified, record['verification'], 'saved exact verification differs')
        statuses[record['result']['status']] += 1

    def at(number, fixed):
        """A reference may contain no restrictions beyond cumulative promises."""
        require(type(number) is int and 0 <= number < len(records), 'invalid oracle reference')
        used.add(number)
        record = records[number]
        _same(record['input']['anchors'], [list(p) for p in sorted(fixed.items())],
             'oracle commitment binding differs')
        return record

    committed = {index[side]: color for side, color in document.get('anchors', {}).items()}
    at(audit['initial_oracle_index'], committed)
    require(len(audit['steps']) == len(result['events']), 'event/step coverage differs')
    counts = {'safe': 0, 'unsafe': 0, 'unknown': 0, 'preexisting_unsat': 0}
    rejections, first_bad = {'exact_unsat': 0, 'unknown': 0}, None
    for number, (event, step) in enumerate(zip(result['events'], audit['steps'])):
        require(step['event_index'] == number, 'step order differs')
        for field in ('kind', 'side', 'symbol', 'before_phase', 'trial_phase', 'after_phase'):
            _same(step[field], event[field], 'event/step identity differs')
        before = at(step['before_oracle_index'], committed)
        proposed = {**committed, index[event['side']]: event['symbol']}
        trial = at(step['trial_oracle_index'], proposed)
        b, t = before['result']['status'], trial['result']['status']
        if event['kind'] == 'reject':
            require(t != 'sat', 'rejected trial has a verified witness')
            extension = 'refuted'
            rejections['exact_unsat' if t == 'unsat' else 'unknown'] += 1
        else:
            extension = ('preexisting_unsat' if b == 'unsat' else
                         'unknown' if 'unknown' in (b, t) else 'unsafe' if t == 'unsat' else 'safe')
            counts[extension] += 1
            committed = proposed
        after = at(step['after_oracle_index'], committed)
        require(step['before_status'] == b and step['after_status'] == after['result']['status']
                and step['extendibility'] == extension, 'extendibility classification differs')
        if extension == 'unsafe' and first_bad is None:
            first_bad = {**step, 'event': event, 'before': before, 'after': after}
    require(used == set(range(len(records))), 'unreferenced oracle certificate')
    _same(audit['commitment_counts'], counts, 'commitment totals differ')
    _same(audit['rejection_counts'], rejections, 'rejection totals differ')
    _same(audit['first_bad_commitment'], first_bad, 'first unsafe evidence differs')
    require(audit['oracle_unknown'] == statuses['unknown'], 'unknown count differs')
    _replay_raw_preservation(document, result, audit, resources)
    return {'passed': True, 'odd_cycle_eq_check': equality_check, 'logical_neq_check': inequality_check, 'producer_runs': 0,
            'oracle_searches': 0, 'oracle_records': len(records), 'oracle_statuses': dict(statuses),
            'phases': phase_count, 'unsafe_commitments': counts['unsafe']}


# The saved schedule and transition checks retain the frozen contract.
# Their policy bindings and contact auditor call use this additive version.

def check_saved_schedule(document, result, geometry, resources):
    """Recheck saved choices with frozen scheduler helpers and no color search.

    This is a shared-code check of the declared scheduling convention, not an
    independent mathematical safety oracle. The caller separately replays the
    relation traces and verifies exact certificates. ``geometry=None`` supports
    old abstract fixtures; actual geometry runs must supply their saved geometry.
    """
    require(digest(result["original_input"]) == digest(document), "schedule original input differs")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1
            and result["policy"] == "quaternary-low-color-triangle-saturation-conditional-v1",
            "saved producer schema/policy differs")
    require(result["probe"] is True and result["oracle_feedback_to_producer"] is False
            and result["old_colors_read"] is False and type(result["backtracks"]) is int
            and result["backtracks"] == 0, "saved producer mode contract differs")
    for name in ("decision_limit", "probe_limit"):
        require(type(result[name]) is int and result[name] >= 0
                and type(resources[name]) is int and result[name] == resources[name],
                "saved producer resource limit differs: " + name)
    expected_schedule = ("mother-peer-with-frame-only-fallback-v1" if geometry is not None
                         else "first-unresolved-input-order-v1")
    require(result["schedule"] == expected_schedule, "saved schedule label differs")
    sides, edges = _edges(document)
    context = None
    if geometry is not None:
        raw_sides, raw_edges, raw_lines = raw_graph(geometry)
        require(sides == raw_sides and edges == raw_edges, "saved schedule geometry identities differ")
        require(digest(sorted(document["lines"], key=lambda row: row["id"]))
                == digest(sorted(raw_lines, key=lambda row: row["id"])),
                "saved schedule physical contacts differ")
        model = build_whole_lines(geometry)
        require(sides == [f"S{i}" for i in range(len(model.plane_map.faces))],
                "saved schedule model face order differs")
        context = model, current_segments(model), level_metadata(model)
    persistent_phases(result)
    choices, probes, rejects = 0, 0, 0
    for event in result["events"]:
        require(choices < resources["decision_limit"] and probes < resources["probe_limit"],
                "saved event after resource exhaustion")
        before = result["phases"][event["before_phase"]]["outcome"]
        require(before["status"] == "underdetermined" and before["side_order"] == sides,
                "saved selection after terminal phase or different side order")
        selected, expected = _selection(sides, before["domains"], context)
        candidates = before["domains"][selected]
        expected.update(side_id=sides[selected], candidate_order=candidates)
        require(digest(event["selection"]) == digest(expected), "saved scheduler metadata differs")
        require(event["side"] == sides[selected] and type(event["symbol"]) is int
                and len(candidates) > 1 and event["symbol"] == min(candidates)
                and event["candidates_before"] == candidates, "saved low-color selection differs")
        probes += 1
        if event["kind"] == "commit":
            choices += 1
        else:
            rejects += 1
    for name, actual in (("choices", choices), ("probes", probes), ("rejections", rejects)):
        require(type(result[name]) is int and result[name] == actual, "saved schedule telemetry differs")
    final = result["phases"][result["final_phase"]]["outcome"]
    if final["status"] == "underdetermined":
        require(choices == resources["decision_limit"] or probes == resources["probe_limit"],
                "saved run stopped before declared resource limit")
        reason = "decision-limit-exhausted" if choices == resources["decision_limit"] else "probe-limit-exhausted"
        require(result["status"] == "incomplete" and result["reason"] == reason,
                "saved resource stop mislabeled")
    else:
        require(final["status"] in ("solved", "conflict") and result["status"] == final["status"],
                "saved terminal status differs")
        reason = ("complete-coloring-verified" if final["status"] == "solved"
                  else "propagation-conflict-under-current-commitments")
        require(result["reason"] == reason, "saved terminal reason differs")
    return {"passed": True, "schedule": expected_schedule, "events_checked": len(result["events"]),
            "producer_rerun": False, "oracle_search_rerun": False,
            "scope": "Frozen scheduler helpers check scheduling metadata; exact safety is checked separately."}


def check_transitions(document, result, stored_phase_audits):
    """Replay saved input mutations and trace certificates, never propagation."""
    _same(result['original_input'], document, 'producer original input changed')
    require(result['probe'] is True and result['oracle_feedback_to_producer'] is False
            and result['backtracks'] == 0, 'guarded/no-feedback contract differs')
    persistent_phases(result)  # Ensures every allocated phase is referenced once.
    phases = result['phases']
    _same(phases[0]['document'], document, 'initial phase differs')
    require(len(phases) == len(stored_phase_audits), 'phase audit coverage differs')
    for phase, stored in zip(phases, stored_phase_audits):
        _same(audit_saturation_contacts(phase['document'], phase['outcome']), stored,
             'saved propagation trace audit differs')
    current, commits, rejects = 0, 0, 0
    for event in result['events']:
        side, color = event['side'], event['symbol']
        before = phases[current]
        require(before['outcome']['status'] == 'underdetermined'
                and event['before_phase'] == current, 'event skips current live phase')
        index = document['sides'].index(side)
        candidates = before['outcome']['domains'][index]
        _same(event['candidates_before'], candidates, 'candidate record differs')
        require(len(candidates) > 1 and color == min(candidates), 'not a low-color unresolved choice')
        require(side not in before['document'].get('anchors', {}), 'overwritten commitment')
        trial_document = deepcopy(before['document'])
        trial_document.setdefault('anchors', {})[side] = color
        trial = phases[event['trial_phase']]
        _same(trial['document'], trial_document, 'trial imports extra restrictions')
        if event['kind'] == 'reject':
            require(trial['outcome']['status'] == 'conflict'
                    and event['extension_claim'] == 'refuted', 'rejection lacks conflict')
            expected = deepcopy(before['document'])
            remaining = [c for c in candidates if c != color]
            expected.setdefault('states', {})[side] = expected_state(remaining, False)['quaternary']
            rejects += 1
        else:
            require(event['kind'] == 'commit' and trial['outcome']['status'] != 'conflict',
                    'invalid committed trial')
            expected = trial_document
            claim = 'complete-witness' if trial['outcome']['status'] == 'solved' else 'inconclusive'
            require(event['extension_claim'] == claim, 'commitment overclaims its trial')
            commits += 1
        current = event['after_phase']
        _same(phases[current]['document'], expected, 'persistent input mutation differs')
    require(result['choices'] == commits and result['rejections'] == rejects
            and result['probes'] == len(result['events']), 'producer counters differ')
    final = phases[current]['outcome']
    for field in ('name_states', 'domains', 'colors'):
        _same(result[field], final[field], 'final phase differs: ' + field)
    require(result['status'] == ('incomplete' if final['status'] == 'underdetermined'
                                else final['status']), 'final status differs')
    return len(phases)
