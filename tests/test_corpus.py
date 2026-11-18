import hashlib
import json

import pytest

from taxcalcbench_pe import corpus


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
