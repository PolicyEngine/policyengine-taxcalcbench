"""Run the complete pinned TY24 comparison."""

import argparse
import json
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile

from .corpus import REVISION, verified_cases
from .finances import add_finances
from .finances import affected_by_limitation as finance_affected
from .households import (
    affected_by_limitation as family_affected,
)
from .households import (
    build_household,
    limitations,
)
from .lines import EXTRA_VARIABLES, LINES, key_limitation, model_amount, read_expected
from .scoring import compare_amount


def evaluate_case(case: Path) -> list[dict]:
    """Calculate the household before loading its reference return."""
    import policyengine as pe

    raw = json.loads((case / "input.json").read_text())
    household = build_household(raw)
    family_limits = limitations(raw)
    finance_limits = add_finances(raw, household)
    if all(person["age"] < 18 for person in household["people"]):
        # A teen may file a tax return with insufficient facts to derive SPM
        # poverty for their household. Request only the federal tax outputs.
        from .model import calculate_federal_outputs

        result = calculate_federal_outputs(household, list(EXTRA_VARIABLES))
    else:
        result = pe.us.calculate_household(
            **household, extra_variables=list(EXTRA_VARIABLES)
        )
    expected = read_expected(case / "output.xml")
    rows = []
    for line in LINES:
        number = line.number
        reasons = [
            reason for reason in family_limits if family_affected(number, reason)
        ]
        reasons.extend(
            reason for reason in finance_limits if finance_affected(number, reason)
        )
        if known := key_limitation(case.name, number):
            reasons.append(known)
        row = compare_amount(
            expected.get(number),
            None if line.unsupported_reason else model_amount(line, result),
            unsupported=line.unsupported_reason,
            limitations=tuple(sorted(set(reasons))),
        )
        rows.append(dict(case=case.name, line=number, label=line.label, **row))
    return rows


def summarize(rows: list[dict]) -> dict:
    """Count statuses and disclose the denominator for each target line."""
    return {
        "statuses": dict(sorted(Counter(r["status"] for r in rows).items())),
        "absent_reference_diagnostics": {
            "eligible": sum(
                r["status"] == "absent_reference" and not r["limitations"] for r in rows
            ),
            "eligible_model_nonzero": sum(
                r["status"] == "absent_reference"
                and not r["limitations"]
                and r["model_rounded"] != 0
                for r in rows
            ),
            "limited": sum(
                r["status"] == "absent_reference" and bool(r["limitations"])
                for r in rows
            ),
        },
        "by_line": {
            line.number: dict(
                sorted(
                    Counter(
                        r["status"] for r in rows if r["line"] == line.number
                    ).items()
                )
            )
            for line in LINES
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path(".cache/tax-calc-bench/tax_calc_bench/ty24/test_data"),
    )
    parser.add_argument(
        "--curated", action="store_true", help="Run the annotated starter cases"
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    cases = verified_cases(args.fixtures)
    focus = {}
    if args.curated:
        focus = json.loads(Path(__file__).with_name("curated.json").read_text())
        cases = [case for case in cases if case.name in focus]
        if {case.name for case in cases} != focus.keys():
            raise ValueError(
                "Curated selection contains a case outside the pinned corpus"
            )
    output = args.out or Path(
        "results/ty24-curated.json" if args.curated else "results/ty24.json"
    )
    rows = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.name}", file=sys.stderr, flush=True)
        rows.extend(evaluate_case(case))
    summary = summarize(rows)
    report = {
        "tax_year": 2024,
        "suite": "curated" if args.curated else "full",
        "curation": focus,
        "synthetic": True,
        "corpus_commit": REVISION,
        "cases": len(cases),
        "packages": {
            k: version(k)
            for k in ("policyengine", "policyengine-us", "policyengine-core")
        },
        "target_lines": len(LINES),
        "summary": summary,
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=output.parent, delete=False) as tmp:
        json.dump(report, tmp, indent=2, allow_nan=False)
        tmp.write("\n")
    Path(tmp.name).replace(output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
