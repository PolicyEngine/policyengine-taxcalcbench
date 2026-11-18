import pytest
from hypothesis import given
from hypothesis import strategies as st

from taxcalcbench_pe.scoring import compare_amount


@given(st.integers(-1_000_000, 1_000_000), st.integers(-1_000_000, 1_000_000))
def test_exact_if_and_only_if_delta_zero(reference, actual):
    row = compare_amount(reference, actual)
    assert row["difference"] == actual - reference
    assert (row["status"] == "exact") == (row["difference"] == 0)


@pytest.mark.parametrize(("actual", "expected"), [(1.49, 1), (1.5, 2), (-1.5, -2)])
def test_rounding(actual, expected):
    assert compare_amount(expected, actual)["status"] == "exact"


def test_only_explicit_supported_determinate_amounts_can_match():
    assert compare_amount(None, 0)["status"] == "absent_reference"
    assert (
        compare_amount(0, 0, limitations=("conflicting answers",))["difference"] is None
    )
    assert (
        compare_amount(0, None, unsupported="refund balance")["status"] == "unsupported"
    )
    with pytest.raises(ValueError):
        compare_amount(0, None)
    with pytest.raises(ValueError):
        compare_amount(0, float("nan"))
