"""Exercise the pinned bundle's one-person federal output path."""

from taxcalcbench_pe.model import calculate_federal_outputs


def test_minor_return_preserves_age_and_uses_requested_columns_only():
    household = {
        "people": [
            {
                "age": 17,
                "employment_income": 29_000,
                "ak_permanent_fund_dividend": 0,
                "is_tax_unit_head": True,
                "is_tax_unit_spouse": False,
                "is_tax_unit_dependent": False,
            }
        ],
        "marital_unit": [{"members": [0]}],
        "tax_unit": {"filing_status": "SINGLE", "head_is_dependent_elsewhere": False},
        "household": {"state_code": "AK"},
        "year": 2024,
        "spm": {"geography_kind": "national"},
    }
    result = calculate_federal_outputs(
        household, ["age", "adjusted_gross_income", "taxable_income"]
    )
    assert result == {
        "person": [{"age": 17}],
        "tax_unit": {"adjusted_gross_income": 29_000, "taxable_income": 14_400},
    }
