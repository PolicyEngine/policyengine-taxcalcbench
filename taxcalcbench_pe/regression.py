"""Check previously confirmed matches against each fresh comparison."""

import json
import sys
from pathlib import Path

BASELINE = Path(__file__).with_name("matched_lines.json")


def check_matches(rows: list[dict], baseline: dict[str, list[str]]) -> list[str]:
    """Identify previously matching cells that changed or disappeared."""
    matches = {(row["case"], row["line"]) for row in rows if row["status"] == "exact"}
    failures = []
    for case, lines in baseline.items():
        for line in lines:
            if (case, line) not in matches:
                failures.append(f"{case}, line {line}")
    return failures


if __name__ == "__main__":
    report = json.loads(Path(sys.argv[1]).read_text())
    baseline = json.loads(BASELINE.read_text())
    if not baseline or any(not lines for lines in baseline.values()):
        raise ValueError("Expected a nonempty baseline of case/line pairs")
    if failures := check_matches(report["rows"], baseline):
        raise SystemExit("Previously matching cells changed:\n" + "\n".join(failures))
