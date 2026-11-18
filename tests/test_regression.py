from taxcalcbench_pe.regression import check_matches


def test_gains_cannot_offset_lost_or_newly_excluded_cells():
    baseline = {"a": ["1a", "11"], "b": ["11"]}
    rows = [
        {"case": "a", "line": "1a", "status": "exact"},
        {"case": "a", "line": "11", "status": "input_or_key_limitation"},
        {"case": "b", "line": "12", "status": "exact"},
    ]
    assert check_matches(rows, baseline) == ["a, line 11", "b, line 11"]
