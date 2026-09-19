"""Check a small graph certificate forcing two nonadjacent side names apart.

This is a post-run explanatory lemma, not a v4 modification or coloring retry.
All nineteen required adjacencies are reconstructed from raw map geometry. The
contradiction uses palette-set deductions, not enumeration of full colorings.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_frontier_restart import file_sha, independent_geometry, read_json
from scripts.validate_relation_frontier_full import require

TARGET = "66b1a56305161b76660d5d2567a7f9720ecde941c8df98f922e594da95d898ed"
MAPPING = {"O": 0, "A": 1, "B": 4, "p": 2, "q": 3, "r": 14, "s": 15, "t": 10, "u": 19}
EDGES = ("O A", "O B", "O p", "A p", "O q", "B q", "p q", "r p", "r q", "r A",
         "s r", "s A", "t O", "t B", "t s", "u B", "u r", "u s", "u t")


def main():
    """Emit a new source-bound certificate for the declared failed drawing."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path,
                        default=ROOT / "outputs/peer-batches-pilot-failure-diagnosis-2026-09-19.json")
    parser.add_argument("--parts", type=Path, default=ROOT / "outputs/peer-batches-full-parts-2026-09-19")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "choose a new gadget certificate output")
    pilot = read_json(args.pilot)
    found = None
    for source in pilot["sources"]:
        path = args.parts / source["filename"]
        require(file_sha(path) == source["sha256"], "referenced checkpoint changed")
        part = read_json(path)
        if TARGET in part["detailed_examples"]:
            found = (part["detailed_examples"][TARGET], source)
            break
    require(found is not None, "declared example missing from pilot evidence")
    detail, source = found
    plane, adjacent = independent_geometry(detail["geometry"])
    require(len(set(MAPPING.values())) == 9, "gadget vertices must be distinct")
    edges = []
    for names in EDGES:
        first, second = names.split()
        a, b = MAPPING[first], MAPPING[second]
        require(b in adjacent[a], "required adjacency missing: " + names)
        raw_edges = [edge for edge in range(len(plane.edges)) if set(plane.shores(edge)) == {a, b}]
        require(bool(raw_edges), "adjacency lacks a real boundary edge")
        edges.append({"vertices": [first, second], "sides": [a, b], "raw_edge_ids": raw_edges})
    require(MAPPING["B"] not in adjacent[MAPPING["A"]], "example's conclusion should be nonlocal")
    # If A=B, O differs from them. Global permutation permits O=1 and A=B=2.
    # Adjacent p/q and s/t each exhaust the two remaining names {3,4}.
    palette = {1, 2, 3, 4}
    pair_palette = palette - {1, 2}
    require(len(pair_palette) == 2, "proof assumes exactly four available names")
    r_domain = palette - ({2} | pair_palette)
    require(r_domain == {1}, "first triangle does not force r=O")
    second_pair_palette = palette - ({2} | r_domain)
    require(second_pair_palette == pair_palette, "second adjacent pair has changed palette")
    u_domain = palette - ({2} | r_domain | second_pair_palette)
    require(not u_domain, "contradiction did not exclude all four names")
    out = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
           "kind": "checked-small-graph-implication", "input_key": TARGET,
           "script_sha256": file_sha(Path(__file__)), "source_checkpoint": source,
           "pilot_evidence": {"filename": args.pilot.name, "sha256": file_sha(args.pilot)},
           "mapping": MAPPING, "required_adjacencies": edges,
           "claim": "For nine distinct vertices with these nineteen edges, every proper coloring "
                    "using at most four names has color(A) != color(B). Additional edges do not hurt the implication.",
           "proof": [
               "Assume A=B=a. Since O is adjacent to A and B, O=o differs from a.",
               "p and q each avoid o and a. They are adjacent, so they exhaust the other two names b,c.",
               "r is adjacent to p,q,A, so r=o.",
               "s avoids r=o and A=a; t avoids O=o and B=a. Since s,t are adjacent, they exhaust b,c.",
               "u is adjacent to B=a,r=o,s,t and therefore sees every available name: contradiction.",
           ],
           "checked_normalized_domains": {"O": [1], "A": [2], "B": [2], "p_q_palette": [3, 4],
                                          "r": sorted(r_domain), "s_t_palette": [3, 4], "u": sorted(u_domain)},
           "application": {"existing_anchor": {"side": 1, "name": 2},
                           "sound_exclusion": {"side": 4, "name": 2},
                           "v4_current_domain_before_fatal_choice": detail["outcome"]["trace"][1]["domain"],
                           "unrelated_nonadjacent_pairs_affected": False},
           "production_attempts_added": 0, "applied_to_v4": False,
           "limits": ["A conditional local implication, not a complete four-coloring algorithm.",
                      "This certificate checks one mapped occurrence; no corpus-wide motif search was performed.",
                      "The pattern may be previously known; no novelty claim is made."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(out, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print({"passed": True, "required_adjacencies_checked": len(edges), "derived_nonlocal_inequality": [1, 4]},
          flush=True)


if __name__ == "__main__":
    main()
