"""TaxCalcBench's 19 TY24 Form 1040 targets and their PolicyEngine US equivalents.

The XML tags follow the pinned upstream tax_return_evaluator.LINES_TO_XPATH_VALUES.
The projections use the TY24 parameters of the locked US model. They apply to the
selected fixtures subject to the adapter's per-line coverage checks.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


@dataclass(frozen=True)
class Line:
    number: str
    label: str
    xml_tag: str
    variables: tuple[str, ...] = ()
    project: Callable[[Any], float] | None = field(default=None, repr=False)
    unsupported_reason: str | None = None


def _filers(result, variable):
    # A dependent's own earnings do not appear on the parent's joint return.
    return sum(
        getattr(person, variable)
        for person in result.person
        if not person.is_tax_unit_dependent
    )


def _line_9(result):
    # PE floors individual gross income components and accounts for deductible
    # losses in loss_ald. Those losses reduce 1040 income on lines 7 and 8.
    return _filers(result, "irs_gross_income") - result.tax_unit.loss_ald


def _line_12(result):
    unit = result.tax_unit
    if unit.tax_unit_itemizes:
        return unit.itemized_taxable_income_deductions + unit.wagering_losses_deduction
    return unit.standard_deduction


def _line_24(result):
    # US places SE tax and the additional Medicare tax under payroll taxes.
    # Its pre-refundable-credit income tax already includes NIIT.
    unit = result.tax_unit
    return (
        unit.income_tax_before_refundable_credits
        + _filers(result, "self_employment_tax")
        + unit.additional_medicare_tax
    )


PAYMENTS_LIMIT = "Withholding, estimated payments and refund allocation lack a complete model mapping."
SCHEDULE_3_LIMIT = "US refundable credits omit form-only Schedule 3 payments and premium-credit reconciliation."


LINES = (
    Line(
        "1a",
        "W-2 wages",
        "WagesAmt",
        ("irs_employment_income", "is_tax_unit_dependent"),
        lambda result: _filers(result, "irs_employment_income"),
    ),
    Line(
        "9",
        "Total income",
        "TotalIncomeAmt",
        ("irs_gross_income", "is_tax_unit_dependent", "loss_ald"),
        _line_9,
    ),
    Line(
        "10",
        "Adjustments to income",
        "TotalAdjustmentsAmt",
        ("above_the_line_deductions", "loss_ald"),
        lambda r: r.tax_unit.above_the_line_deductions - r.tax_unit.loss_ald,
    ),
    Line(
        "11",
        "Adjusted gross income",
        "AdjustedGrossIncomeAmt",
        ("adjusted_gross_income",),
    ),
    Line(
        "12",
        "Standard or itemized deduction",
        "TotalItemizedOrStandardDedAmt",
        (
            "tax_unit_itemizes",
            "standard_deduction",
            "itemized_taxable_income_deductions",
            "wagering_losses_deduction",
        ),
        _line_12,
    ),
    Line("15", "Taxable income", "TaxableIncomeAmt", ("taxable_income",)),
    # The regular-rate tax and preferential capital-gains tax precede AMT.
    Line(
        "16",
        "Tax",
        "TaxAmt",
        ("income_tax_main_rates", "capital_gains_tax"),
        lambda r: r.tax_unit.income_tax_main_rates + r.tax_unit.capital_gains_tax,
    ),
    Line(
        "19",
        "Child tax credit and credit for other dependents",
        "CTCODCAmt",
        ("non_refundable_ctc", "ctc_limiting_tax_liability"),
        lambda r: min(
            r.tax_unit.non_refundable_ctc, r.tax_unit.ctc_limiting_tax_liability
        ),
    ),
    Line(
        "24",
        "Total tax",
        "TotalTaxAmt",
        (
            "income_tax_before_refundable_credits",
            "self_employment_tax",
            "is_tax_unit_dependent",
            "additional_medicare_tax",
        ),
        _line_24,
    ),
    Line("25d", "Withholding", "WithholdingTaxAmt", unsupported_reason=PAYMENTS_LIMIT),
    Line(
        "26",
        "Estimated payments",
        "EstimatedTaxPaymentsAmt",
        unsupported_reason=PAYMENTS_LIMIT,
    ),
    Line("27", "Earned income credit", "EarnedIncomeCreditAmt", ("eitc",)),
    Line(
        "28",
        "Additional child tax credit",
        "AdditionalChildTaxCreditAmt",
        ("refundable_ctc",),
    ),
    Line(
        "29",
        "Refundable American opportunity credit",
        "RefundableAmerOppCreditAmt",
        ("refundable_american_opportunity_credit",),
    ),
    Line(
        "32",
        "Other payments and refundable credits",
        "RefundableCreditsAmt",
        unsupported_reason=SCHEDULE_3_LIMIT,
    ),
    Line("33", "Total payments", "TotalPaymentsAmt", unsupported_reason=PAYMENTS_LIMIT),
    Line("34", "Overpayment", "OverpaidAmt", unsupported_reason=PAYMENTS_LIMIT),
    Line("35a", "Refund", "RefundAmt", unsupported_reason=PAYMENTS_LIMIT),
    Line("37", "Amount owed", "OwedAmt", unsupported_reason=PAYMENTS_LIMIT),
)

EXTRA_VARIABLES = tuple(sorted({v for line in LINES for v in line.variables}))


def model_amount(line: Line, result: Any) -> float:
    """Project one supported 1040 concept from a calculate_household result."""
    if line.unsupported_reason:
        raise ValueError(line.unsupported_reason)
    if line.project:
        return float(line.project(result))
    (variable,) = line.variables
    return float(getattr(result.tax_unit, variable))


def read_expected(xml_path: Path) -> dict[str, int]:
    """Read explicitly reported dollar amounts from the TY24 reference return."""
    root = ElementTree.parse(xml_path).getroot()
    forms = root.findall("ReturnData/IRS1040")
    if (
        root.tag != "Return"
        or root.findtext("ReturnHeader/TaxYr") != "2024"
        or len(forms) != 1
    ):
        raise ValueError(f"Expected one TY24 Form 1040 in {xml_path}")
    expected = {}
    for line in LINES:
        elements = forms[0].findall(line.xml_tag)
        if not elements:
            continue
        if len(elements) != 1:
            raise ValueError(f"Duplicate {line.xml_tag} in {xml_path}")
        try:
            expected[line.number] = int(elements[0].text or "")
        except ValueError as error:
            raise ValueError(f"Invalid {line.xml_tag} in {xml_path}") from error
    return expected


_CONFLICTING_ANSWERS = frozenset(
    {
        "mfj-dependent-claimed-2441-exclusion",
        "mfj-w2-box12-codes-a-b-1099int-schedulec",
        "single-senior-blind-over-65",
    }
)


def key_limitation(case_id: str, number: str) -> str | None:
    """Name known upstream missing/conflicting facts on affected targets."""
    issues = []
    if case_id in _CONFLICTING_ANSWERS and number not in {"1a", "9", "25d"}:
        # The disputed educator expense changes AGI and may change itemized
        # deductions and credits; the disputed estimate changes payments.
        issues.append(
            "TaxCalcBench #161: conflicting educator/estimated-payment inputs"
        )
    if case_id == "single-senior-blind-over-65" and number in {
        "24",
        "32",
        "33",
        "34",
        "35a",
        "37",
    }:
        issues.append("TaxCalcBench #66: missing Form 1095-A details")
    return " | ".join(issues) or None
