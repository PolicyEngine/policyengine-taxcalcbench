from types import SimpleNamespace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from taxcalcbench_pe.lines import LINES, key_limitation, model_amount, read_expected


def line(number):
    return next(line for line in LINES if line.number == number)


def test_omitted_zero_and_schedule_values_are_distinct(tmp_path):
    path = tmp_path / "output.xml"
    path.write_text(
        "<Return><ReturnHeader><TaxYr>2024</TaxYr></ReturnHeader><ReturnData>"
        "<IRS1040><TaxAmt>0</TaxAmt><AdjustedGrossIncomeAmt>-50</AdjustedGrossIncomeAmt>"
        "</IRS1040><Schedule><WagesAmt>250</WagesAmt></Schedule></ReturnData></Return>"
    )
    assert read_expected(path) == {"11": -50, "16": 0}


@pytest.mark.parametrize("bad_amount", ["", "garbage", "1.7", "NaN"])
def test_malformed_reference_is_an_error(tmp_path, bad_amount):
    path = tmp_path / "output.xml"
    path.write_text(
        "<Return><ReturnHeader><TaxYr>2024</TaxYr></ReturnHeader><ReturnData>"
        f"<IRS1040><TaxAmt>{bad_amount}</TaxAmt></IRS1040></ReturnData></Return>"
    )
    with pytest.raises(ValueError, match="TaxAmt"):
        read_expected(path)


@given(
    gross=st.integers(0, 1000000),
    loss=st.integers(0, 100000),
    adjustments=st.integers(0, 100000),
)
def test_reclassifying_losses_preserves_adjusted_gross_income(gross, loss, adjustments):
    # The model includes losses among its above-the-line deductions. Form 1040
    # places them among income on line 9. The two definitions of AGI must agree.
    result = SimpleNamespace(
        person=[SimpleNamespace(irs_gross_income=gross, is_tax_unit_dependent=False)],
        tax_unit=SimpleNamespace(
            loss_ald=loss,
            above_the_line_deductions=loss + adjustments,
            adjusted_gross_income=gross - loss - adjustments,
        ),
    )
    assert model_amount(line("9"), result) - model_amount(
        line("10"), result
    ) == model_amount(line("11"), result)


def test_nonrefundable_credit_is_limited_by_liability():
    result = SimpleNamespace(
        tax_unit=SimpleNamespace(
            non_refundable_ctc=1200, ctc_limiting_tax_liability=400
        )
    )
    assert model_amount(line("19"), result) == 400


def test_issue_161_quarantines_downstream_lines_but_keeps_wages_and_total_income():
    case = "mfj-dependent-claimed-2441-exclusion"
    for n in ("10", "11", "15", "16", "24", "26", "37"):
        assert "#161" in key_limitation(case, n)
    for n in ("1a", "9"):
        assert key_limitation(case, n) is None
