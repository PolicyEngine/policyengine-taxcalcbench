"""Check financial mappings against synthetic source documents."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from taxcalcbench_pe.finances import add_finances, affected_by_limitation


def questionnaire(**forms):
    return {
        "input": {
            "return_data": {
                "irs1040": {"filing_status": {"value": "married_jointly"}},
                **forms,
            }
        }
    }


def filers():
    return {"people": [{}, {}], "tax_unit": {}}


@given(wages=st.integers(0, 120000), deferral=st.integers(0, 10000))
def test_w2_deferral_does_not_reduce_box_one_again(wages, deferral):
    raw = questionnaire(
        w2=[
            {
                "who_applies_to": {"value": "spouse"},
                "wages": {"value": wages},
                "medicare_wages_and_tips": {"value": wages + deferral},
                "social_security_wages": {"value": wages + deferral},
                "employers_use_grp": [
                    {
                        "box_12_code": {"value": "D"},
                        "box_12_amount": {"value": deferral},
                    }
                ],
            }
        ]
    )
    hh = filers()
    assert not add_finances(raw, hh)
    spouse = hh["people"][1]
    assert (
        spouse["employment_income"] - spouse["traditional_401k_contributions_desired"]
        == wages
    )
    assert spouse["payroll_tax_gross_wages"] == wages + deferral


def test_return_totals_preserve_document_ownership_and_exclude_double_counted_dividends():
    raw = questionnaire(
        irs1040_schedule1={
            "irs1099_g": [
                {
                    "g_who_applies_to": "spouse",
                    "g_unemployment_comp": 500,
                    "g_amount_repaid_current_year": 100,
                }
            ]
        },
        irs1040_scheduleb={
            "irs1099_int": [
                {
                    "interest_1099int_who_applies_to": "joint",
                    "interest_1099int_interest": 99,
                }
            ],
            "irs1099_div": [
                {
                    "dividend_1099div_who_applies_to": "taxpayer",
                    "dividend_1099div_ordinary_div": 80,
                    "dividend_1099div_qualified_div": 73,
                }
            ],
        },
    )
    hh = filers()
    assert not add_finances(raw, hh)
    head, spouse = hh["people"]
    assert head["qualified_dividend_income"] == 73
    assert head["non_qualified_dividend_income"] == 7
    assert head["taxable_interest_income"] + spouse["taxable_interest_income"] == 99
    assert spouse["unemployment_compensation"] == 400
    assert "unemployment_compensation" not in head


def test_business_separates_receipts_withholding_expenses_and_qbi():
    raw = questionnaire(
        irs1040_schedulec=[
            {
                "who_applies_to": "spouse",
                "gross_receipts_cash": 1200,
                "other_income": 10,
                "irs1099_nec": [{"nec_comp": 400, "nec_fed_wh": 50}],
                "irs1099_k": [{"k_comp": 250}],
                "returns_allowances": 30,
                "advertising": 100,
                "other_expense_detail": [{"other_expense_detail_amt": 20}],
                "specified_service": True,
                "wages_paid": 10,
                "wages_expense": 25,
                "se_health_insurance": 50,
                "former_employer": True,
            }
        ]
    )
    hh = filers()
    reasons = add_finances(raw, hh)
    assert hh["people"][1]["sstb_self_employment_income"] == 1685
    assert hh["people"][1]["self_employed_health_insurance_premiums"] == 50
    assert len(reasons) == 1
    assert affected_by_limitation("15", reasons[0])
    assert not affected_by_limitation("9", reasons[0])


def test_disputed_educator_answer_is_visible_and_wages_remain_comparable():
    raw = questionnaire(
        irs1040_schedule1={"qualified_educator": False, "tp_educator_exp_amount": 200}
    )
    hh = filers()
    [reason] = add_finances(raw, hh)
    assert affected_by_limitation("11", reason)
    assert not affected_by_limitation("1a", reason)
    assert "educator_expense" not in hh["people"][0]


@pytest.mark.parametrize(
    ("bought", "sold", "term", "conflicting"),
    [
        ("2024-05-05", "2024-06-06", "long_term", True),
        ("2023-02-28", "2024-02-28", "short_term", False),
        ("2023-02-28", "2024-02-29", "short_term", True),
        ("2020-02-29", "2021-02-28", "short_term", False),
        ("2020-02-29", "2021-03-01", "long_term", False),
        (None, None, "long_term", False),
    ],
)
def test_1099b_checks_reported_term_without_changing_net_gain(
    bought, sold, term, conflicting
):
    raw = questionnaire(
        irs8949={
            "irs1099_b_grp": [
                {
                    "who_applies_to": "taxpayer",
                    "irs1099_b": [
                        {
                            "input_sale_term": term,
                            "acquired_dt": bought,
                            "sold_disposed_dt": sold,
                            "proceeds": 10000,
                            "cost_basis": 1000,
                        }
                    ],
                }
            ]
        }
    )
    household = filers()
    reasons = add_finances(raw, household)
    assert household["people"][0][term + "_capital_gains"] == 9000
    assert bool(reasons) == conflicting
    if conflicting:
        [reason] = reasons
        assert all(affected_by_limitation(line, reason) for line in ("15", "16", "24"))
        assert all(
            not affected_by_limitation(line, reason)
            for line in ("1a", "9", "10", "11", "27", "29")
        )
