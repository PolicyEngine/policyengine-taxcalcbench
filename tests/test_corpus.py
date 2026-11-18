import hashlib
import json

import pytest

from taxcalcbench_pe import corpus
from taxcalcbench_pe.lines import LINES


def test_curated_cases_use_pinned_inputs_supported_lines_and_sources():
    selection = json.loads(corpus.MANIFEST.with_name("curated.json").read_text())
    roster = json.loads(corpus.MANIFEST.read_text())
    supported = {line.number for line in LINES if not line.unsupported_reason}
    assert selection and selection.keys() <= roster.keys()
    for case in selection.values():
        assert case["focus_lines"] and set(case["focus_lines"]) <= supported
        assert case["question"] and case["source"].startswith("https://www.irs.gov/")


def test_refuses_changed_reference_or_partial_roster(tmp_path, monkeypatch):
    fixture = tmp_path / "fixtures"
    case = fixture / "example"
    case.mkdir(parents=True)
    key = case / "output.xml"
    key.write_bytes(b"original")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"example": {"output.xml": hashlib.sha256(key.read_bytes()).hexdigest()}}
        )
    )
    monkeypatch.setattr(corpus, "MANIFEST", manifest)
    assert corpus.verified_cases(fixture) == [case]
    key.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="checksum"):
        corpus.verified_cases(fixture)
    (fixture / "extra").mkdir()
    with pytest.raises(ValueError, match="roster"):
        corpus.verified_cases(fixture)
