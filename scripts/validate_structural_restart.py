"""Independent geometry, set-relation and equality-refutation proof replay.

No producer's contraction implementation or mask-composition implementation is
used below. Quotient classes are rebuilt as ordinary sets from the real edges.
An inconclusive structural query is checked for saturation, not called a
certificate that equal names can extend to a complete map.
"""

from collections import Counter
from itertools import combinations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import (
    anchored_domains, complete_subsets, independent_geometry, json_value, verify_result,
)
from scripts.validate_level_sides_peer import audit_choice
from scripts.validate_relation_frontier import (
    allowed_relations, check_relational_fixed_point, decode, decoded_matrix, replay_hall,
)


def require(condition, message):
    """Keep new audit conditions active even under optimized Python."""
    if not condition:
        raise AssertionError(message)


def audit_refutation(vertex_count, edges, first, second, certificate):
    """Check a four-name proof using independent set partitions and raw edges."""
    raw = {frozenset(edge) for edge in edges}
    require(certificate["schema_version"] == 1 and certificate["palette_size"] == 4
            and certificate["rule"] == "four-name-shared-triangle-refutation-v1",
            "wrong certificate schema or palette")
    require(certificate["vertex_count"] == vertex_count and certificate["assumed_equal"]
            == sorted((first, second)), "different same-name hypothesis")
    require(first != second and all(0 <= v < vertex_count for v in (first, second)), "bad hypothesis")
    groups = [{i} for i in range(vertex_count) if i not in (first, second)] + [{first, second}]

    def actual_group(members):
        """A proof must name a whole current equivalence class, not a subset."""
        require(members == sorted(set(members)), "noncanonical class")
        target = set(members)
        require(target in groups, "proof names a nonexistent current class")
        return target

    def adjacent(a, b):
        """Quotient adjacency exists only when some original edge witnesses it."""
        return any(frozenset((u, v)) in raw for u in a for v in b)

    def audit_witness(witness, a, b):
        """Check actual source endpoints, orientation-independent class pairing."""
        require({frozenset(c) for c in witness["classes"]} == {frozenset(a), frozenset(b)},
                "edge witness names the wrong quotient classes")
        edge = witness["original_edge"]
        require(len(edge) == 2 and frozenset(edge) in raw, "witness invents an original edge")
        u, v = edge
        require((u in a and v in b) or (v in a and u in b), "witness endpoints are in wrong classes")

    def audit_edges(witnesses, pairs):
        """Require exact, unique coverage of the stated quotient-edge premises."""
        keys = {frozenset((frozenset(a), frozenset(b))) for a, b in pairs}
        got = [frozenset(frozenset(c) for c in w["classes"]) for w in witnesses]
        require(len(got) == len(keys) and set(got) == keys, "missing or duplicate edge premise")
        for witness in witnesses:
            a, b = map(actual_group, witness["classes"])
            audit_witness(witness, a, b)

    for step in certificate["merges"]:
        a, b = actual_group(step["first_class"]), actual_group(step["second_class"])
        triangle = [actual_group(c) for c in step["triangle"]]
        require(len({frozenset(c) for c in [a, b, *triangle]}) == 5,
                "a shared-triangle premise needs five distinct classes")
        require(all(adjacent(x, y) for x, y in combinations(triangle, 2))
                and all(adjacent(x, y) for x in (a, b) for y in triangle), "missing triangle or spoke")
        require(not adjacent(a, b), "producer merged two already adjacent classes")
        audit_edges(step["triangle_edges"], list(combinations(triangle, 2)))
        audit_edges(step["spokes"], [(x, y) for x in (a, b) for y in triangle])
        require(step["result_class"] == sorted(a | b), "wrong equality-union result")
        groups.remove(a)
        groups.remove(b)
        groups.append(a | b)
    require(certificate["final_classes"] == sorted((sorted(g) for g in groups)),
            "final equivalence partition differs")
    contradiction = certificate["contradiction"]
    if certificate["status"] == "proved_different":
        require(contradiction is not None, "claimed refutation has no contradiction")
        if contradiction["kind"] == "self_loop":
            group = actual_group(contradiction["class"])
            edge = contradiction["original_edge"]
            require(len(edge) == 2 and frozenset(edge) in raw and set(edge) <= group,
                    "false same-class conflict")
        else:
            require(contradiction["kind"] == "five_clique", "unsupported contradiction")
            clique = [actual_group(c) for c in contradiction["classes"]]
            require(len(clique) == len({frozenset(c) for c in clique}) == 5, "not five distinct classes")
            pairs = list(combinations(clique, 2))
            require(all(adjacent(a, b) for a, b in pairs), "not a five-clique")
            audit_edges(contradiction["edges"], pairs)
    else:
        require(certificate["status"] == "inconclusive" and contradiction is None,
                "unrecognized structural outcome")
        require(not any(edge <= group for edge in raw for group in groups), "missed self-loop")
        # Build a fresh quotient adjacency once.  Repeated scans of raw edge
        # witnesses inside every triple would dominate full-corpus checking.
        owner = {vertex: i for i, group in enumerate(groups) for vertex in group}
        neighbors = [set() for _ in groups]
        for edge in raw:
            a, b = (owner[v] for v in edge)
            neighbors[a].add(b)
            neighbors[b].add(a)
        for a, b, c in combinations(range(len(groups)), 3):
            if b not in neighbors[a] or c not in neighbors[a] or c not in neighbors[b]:
                continue
            common = neighbors[a] & neighbors[b] & neighbors[c]
            require(len(common) < 2, "inconclusive query stopped before saturation")
    stats = certificate["statistics"]
    require(stats["forced_merges"] == len(certificate["merges"])
            and stats["final_class_count"] == len(groups) and stats["input_edges"] == len(raw),
            "wrong structural proof statistics")
    require(stats["passes"] == len(certificate["merges"]) + 1
            and type(stats["triangles_examined"]) is int
            and stats["triangles_examined"] >= len(certificate["merges"]), "invalid producer work counters")
    return {"passed": True, "forced_merges": len(certificate["merges"]),
            "conclusion": certificate["status"],
            "triangles_examined_scope": "producer telemetry; type/lower bound checked, exact count not replayed"}


def audit_propagation(plane, adjacent, anchors, learned, outcome, subsets):
    """Replay Hall and ordered-pair deletions, inserting only certified NEQ."""
    domains, previous, stats = anchored_domains(plane, anchors), None, Counter()
    require(outcome["learned_pairs"] == learned and outcome["palette"] == [1, 2, 3, 4]
            and outcome["choices"] == outcome["backtracks"] == 0, "invalid propagation metadata")
    require(bool(outcome["phases"]), "missing propagation")
    for index, phase in enumerate(outcome["phases"]):
        require(anchored_domains(plane, phase["hall_input_anchors"]) == domains, "different Hall input")
        if index == 0:
            require(json_value(phase["hall_input_anchors"]) == json_value(anchors), "different commitments")
        hall_domains, hall_conflict, count = replay_hall(plane, adjacent, domains, phase, subsets)
        stats["hall_events"] += count
        allowed = allowed_relations(hall_domains, adjacent)
        work = allowed if previous is None else [[a & b for a, b in zip(row, permitted)]
                                                for row, permitted in zip(previous, allowed)]
        require(work == decoded_matrix(phase["pre_structural_relations"], len(domains)),
                "pre-structural matrix differs")
        deductions = []
        for a, b in learned:
            before = work[a][b]
            after = {(x, y) for x, y in before if x != y}
            if after != before:
                deductions.append((a, b, before, after))
                work[a][b], work[b][a] = after, {(y, x) for x, y in after}
        require(len(deductions) == len(phase["structural_trace"]), "missing structural deletion")
        for event, (a, b, before, after) in zip(phase["structural_trace"], deductions):
            require(event["pair"] == [a, b] and decode(event["before"]) == before
                    and decode(event["after"]) == after and decode(event["removed"]) == before - after,
                    "invalid learned-inequality deletion")
        require(work == decoded_matrix(phase["relation_input"], len(domains)), "wrong pair-closure input")
        if hall_conflict or any(not cell for row in work for cell in row):
            require(not phase["relation_trace"], "pair propagation after known conflict")
        for event in phase["relation_trace"]:
            require(all(cell for row in work for cell in row), "pair event after contradiction")
            i, j, k = event["i"], event["j"], event["via"]
            before, left, right = work[i][j], work[i][k], work[k][j]
            require(decode(event["before"]) == before and decode(event["left"]) == left
                    and decode(event["right"]) == right, "wrong relation premise")
            support = {(a, b) for a, c in left for middle, b in right if c == middle}
            after = before & support
            require(after != before and decode(event["after"]) == after
                    and decode(event["removed"]) == before - after, "incorrect relation deletion")
            work[i][j], work[j][i] = after, {(b, a) for a, b in after}
            stats["relation_events"] += 1
        conflict = hall_conflict or any(not cell for row in work for cell in row)
        require(phase["relation_conflict"] is conflict, "wrong propagation conflict label")
        domains = [{a for a, b in work[i][i]} for i in range(len(domains))]
        if not conflict:
            check_relational_fixed_point(work)
        if index + 1 < len(outcome["phases"]):
            require(not conflict and domains != hall_domains, "unnecessary propagation loop")
        else:
            require(conflict or domains == hall_domains, "premature propagation stop")
        previous = work
        stats["filter_phases"] += 1
    status = "conflict" if conflict else "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
    require(outcome["status"] == status and outcome["domains"] == [sorted(d) for d in domains],
            "wrong final propagation status or domains")
    require(decoded_matrix(outcome["relations"], len(domains)) == previous
            and outcome["hall_conflict"] == outcome["phases"][-1]["hall_conflict"], "wrong final propagation")
    return [sorted(d) for d in domains], stats


def verify_run(geometry, result):
    """Verify actual geometry, all structural queries and every chosen action."""
    require(not sys.flags.optimize, "legacy independent checkers require Python without -O")
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    units = current_segments(model)
    contacts, _ = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    require(set(result["levels"]) == set(generations), "mother metadata coverage differs")
    for name, item in generations.items():
        require(result["levels"][name]["level"] == (None if item["depth"] is None else item["depth"] + 1)
                and result["levels"][name]["parents"] == item["parents"]
                and result["levels"][name]["endpoint_contacts"] == contacts[name], "different mother metadata")
    require(json_value(result["units"]) == json_value(units), "different mother intervals")
    require(result["unranked_mothers"] == sorted(name for name, item in generations.items()
                                                if item["depth"] is None), "unranked mothers differ")
    require(type(result["structural"]) is bool and result["policy"] == "mother-peer-structural-reuse-v1"
            + ("" if result["structural"] else "-disabled"), "wrong declared policy")
    require(result["backtracks"] == 0 and result["old_colors_read"] is False
            and result["local_budget"] is None, "unexpected retry, local budget or old colors")
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    require(plane.face_of_dart[first] == geometry["outerFace"]
            and json_value(result["initial_anchors_by_dart"]) == json_value(anchors), "wrong initialization")
    edges = [(a, b) for a in range(len(adjacent)) for b in sorted(adjacent[a]) if a < b]
    expected_sources = [{"pair": [a, b], "raw_edge_ids": [e for e in range(len(plane.edges))
                         if set(plane.shores(e)) == {a, b}]} for a, b in edges]
    require(result["geometric_edge_sources"] == expected_sources, "structural graph lacks true boundary sources")
    calls, queries = result["propagation_phases"], result["proof_queries"]
    require(len(calls) == len(result["events"]) + 1, "missing or invented propagation calls")
    subsets, learned, seen, commits, stats = complete_subsets(adjacent), [], {}, [], Counter()
    require(calls[0]["learned_pairs"] == [], "unproved initial relation")
    require(json_value(calls[0]["anchors_by_dart"]) == json_value(anchors), "wrong first commitments")
    domains, counts = audit_propagation(plane, adjacent, anchors, learned, calls[0]["outcome"], subsets)
    stats.update(counts)
    for call_index, (event, call) in enumerate(zip(result["events"], calls[1:]), 1):
        require(calls[call_index - 1]["outcome"]["status"] == "underdetermined", "action after terminal status")
        require(any(len(domain) > 1 for domain in domains) and all(domains), "action after termination")
        proposal = event["proposal"]
        audit_choice(model, units, result["levels"], domains, adjacent, proposal)
        side, symbol = proposal["side"], proposal["symbol"]
        require(plane.face_of_dart[proposal["dart"]] == side, "proposal dart does not name chosen side")
        candidates = [other for other, values in enumerate(domains) if other != side and values == [symbol]]
        if not result["structural"]:
            candidates = []
        found, expected_checks = None, []
        for other in candidates:
            pair = tuple(sorted((side, other)))
            cached = pair in seen
            if not cached:
                index = len(seen)
                require(index < len(queries) and queries[index]["pair"] == list(pair), "query coverage/order differs")
                certificate = queries[index]["certificate"]
                audit_refutation(len(adjacent), edges, *pair, certificate)
                seen[pair] = index
            index = seen[pair]
            expected_checks.append({"other_side": other, "pair": list(pair), "query_index": index, "cached": cached})
            if queries[index]["certificate"]["status"] == "proved_different":
                require(list(pair) not in learned, "repeated learned pair")
                learned.append(list(pair))
                found = list(pair)
                break
        require(event["checks"] == expected_checks and event["learned_pair"] == found, "different structural query scan")
        if found is None:
            require(event["kind"] == "commit", "missing actual name commitment")
            commits.append(proposal)
            anchors[proposal["dart"]] = [symbol]
        else:
            require(event["kind"] == "learn_relation", "refuted proposal was committed")
        require(call["learned_pairs"] == learned
                and json_value(call["anchors_by_dart"]) == json_value(anchors), "post-action state differs")
        domains, counts = audit_propagation(plane, adjacent, anchors, learned, call["outcome"], subsets)
        stats.update(counts)
    require(len(seen) == len(queries) and result["learned_pairs"] == learned, "unused or missing proof queries")
    require(result["trace"] == commits and result["choices"] == len(commits), "committed trace differs")
    require(json_value(result["anchors_by_dart"]) == json_value(anchors), "final committed names differ")
    last = calls[-1]["outcome"]
    require(last["status"] in ("solved", "conflict"), "unfinished policy run")
    for key in ("status", "domains", "relations", "hall_conflict"):
        require(result[key] == last[key], "final field differs: " + key)
    expected_stats = {"unique_structural_queries": len(queries),
                      "query_checks": sum(len(e["checks"]) for e in result["events"]),
                      "cache_hits": sum(c["cached"] for e in result["events"] for c in e["checks"]),
                      "learned_relations": len(learned)}
    require(result["statistics"] == expected_stats, "wrong structural statistics")
    legality = verify_result(geometry, result, (plane, adjacent)) if result["status"] == "solved" else None
    require(legality is not None or result["colors"] is None, "failed run supplied an unverified answer")
    return {"passed": True, "structural_queries_checked": len(queries),
            "learned_relations_checked": len(learned), "actual_commits_checked": len(commits),
            "final_legality": legality, **stats}
