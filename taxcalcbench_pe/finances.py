"""Map the financial questionnaire and tax documents for the pinned TY2024 corpus.

Only input.json enters this module. Each limitation names the first affected tax
concept. The scorer can retain comparisons of independently supported lines.
"""

from collections import defaultdict
from datetime import date


def _values(obj):
    if isinstance(obj, list):
        return [_values(v) for v in obj]
    if isinstance(obj, dict):
        if "value" in obj:
            return obj["value"]
        return {k: _values(v) for k, v in obj.items()}
    return obj


def _add(entity, variable, amount):
    entity[variable] = entity.get(variable, 0) + amount


def _owner(people, owner):
    return people[{"taxpayer": 0, "spouse": 1}[owner]]


# Conservative propagation to the 19 upstream 1040 targets. Income can affect
# the taxable share of Social Security, the student loan deduction, credits,
# and the itemize-or-standard election; payments cannot affect income.
_PAYMENTS = {"33", "34", "35a", "37"}
_TAX = {"24", "34", "35a", "37"}
_CREDITS = _TAX | _PAYMENTS | {"19", "27", "28", "29", "32"}
_QBI = _CREDITS | {"15", "16"}
_AGI = _QBI | {"9", "10", "11", "12"}
_EFFECTS = {
    "business": _AGI,
    "capital": _AGI,
    # Term changes the preferential rate and the taxable-income limit on QBI.
    # The combined Schedule D gain, AGI, and EITC investment income are invariant.
    "holding period": _QBI - {"27", "29"},
    "educator": _AGI,
    "student loan": _AGI,
    "dependent care": _AGI,  # taxable unused carryover can enter 1040 line 1e
    "QBI": _QBI,
    "marketplace": _CREDITS,  # can change tax or a refundable credit
    "uncollected FICA": _TAX,
    "excess FICA": _PAYMENTS | {"32"},
    "estimated payment": _PAYMENTS | {"26"},
}


def affected_by_limitation(line_number: str, reason: str) -> bool:
    """Whether a financial input limitation can affect this 1040 line."""
    return line_number in _EFFECTS[reason.split(": ", 1)[0]]


def _wages(data, people, tax_unit, reasons):
    social_security_wages = defaultdict(float)
    ss_withheld = defaultdict(lambda: defaultdict(float))
    for w2 in data.get("w2", []):
        owner = w2["who_applies_to"]
        person = _owner(people, owner)
        deferrals = 0
        for item in w2.get("employers_use_grp", []):
            code, amount = item["box_12_code"], item["box_12_amount"]
            if code == "D":
                deferrals += amount
            elif code in {"A", "B", "M", "N"} and amount:
                reasons.add("uncollected FICA: W-2 box 12 amounts on Schedule 2")
        # Box 1 already excludes elective deferrals. PE's employment_income
        # starts before deferrals and its irs_employment_income deducts them.
        _add(person, "employment_income", w2.get("wages", 0) + deferrals)
        _add(person, "traditional_401k_contributions_desired", deferrals)
        _add(person, "payroll_tax_gross_wages", w2.get("medicare_wages_and_tips", 0))
        social_security_wages[owner] += w2.get("social_security_wages", 0) + w2.get(
            "social_security_tips", 0
        )
        ss_withheld[owner][w2.get("ein")] += w2.get("social_security_tax", 0)
        for loc in w2.get("w2_state_local_tax_grp", []):
            _add(tax_unit, "state_withheld_income_tax", loc.get("state_income_tax", 0))
            _add(tax_unit, "local_income_tax", loc.get("local_income_tax", 0))
    for owner, wages in social_security_wages.items():
        # TY24 wage base and employee rate: https://www.ssa.gov/news/en/cola/factsheets/2024.html
        _owner(people, owner)["taxable_earnings_for_social_security"] = min(
            wages, 168600
        )
        if sum(ss_withheld[owner].values()) > 10453.20:
            reasons.add(
                "excess FICA: employee Social Security withholding over the annual cap"
            )


def _investment(data, people, reasons):
    schedule_b = data.get("irs1040_scheduleb", {})
    for row in schedule_b.get("irs1099_int", []):
        owner = row["interest_1099int_who_applies_to"]
        # The pinned joint account belongs to taxpayers filing jointly; the
        # equal allocation preserves their joint taxable interest and penalty.
        owners = people[:2] if owner == "joint" else [_owner(people, owner)]
        for p in owners:
            _add(
                p,
                "taxable_interest_income",
                row.get("interest_1099int_interest", 0) / len(owners),
            )
            _add(
                p,
                "early_withdrawal_penalty",
                row.get("interest_1099int_early_withdrawal", 0) / len(owners),
            )
    for row in schedule_b.get("irs1099_div", []):
        p = _owner(people, row["dividend_1099div_who_applies_to"])
        qualified = row.get("dividend_1099div_qualified_div", 0)
        _add(p, "qualified_dividend_income", qualified)
        _add(
            p,
            "non_qualified_dividend_income",
            row.get("dividend_1099div_ordinary_div", 0) - qualified,
        )
        _add(
            p,
            "long_term_capital_gains",
            row.get("dividend_1099div_capital_gain_distr", 0),
        )
        if row.get("dividend_1099div_nondividend_distributions"):
            reasons.add("capital: cost basis for nondividend distribution unavailable")
    for group in data.get("irs8949", {}).get("irs1099_b_grp", []):
        p = _owner(people, group["who_applies_to"])
        for sale in group["irs1099_b"]:
            term = sale["input_sale_term"]
            if sale.get("acquired_dt") and sale.get("sold_disposed_dt"):
                bought = date.fromisoformat(sale["acquired_dt"])
                sold = date.fromisoformat(sale["sold_disposed_dt"])
                # The day after the anniversary begins the long-term period.
                # Comparing calendar components handles a February 29 purchase.
                anniversary = (bought.year + 1, bought.month, bought.day)
                long_term = (sold.year, sold.month, sold.day) > anniversary
                if (term == "long_term") != long_term:
                    reasons.add(
                        "holding period: 1099-B sale term conflicts with transaction dates"
                    )
            name = {
                "long_term": "long_term_capital_gains",
                "short_term": "short_term_capital_gains",
            }[term]
            gain = sale["proceeds"] - sale["cost_basis"]
            wash = sale.get("wash_sale_loss", 0)
            discount = sale.get("accrued_market_discount", 0)
            # Form 8949 columns (f)-(g): market discount is taxable interest
            # up to realized gain. A disallowed wash loss increases the recognized gain.
            discount_interest = min(discount, max(gain, 0))
            if wash > max(-gain, 0):
                reasons.add("capital: 1099-B reports wash loss exceeding realized loss")
            _add(p, name, gain + wash - discount_interest)
            _add(p, "taxable_interest_income", discount_interest)
    schedule_d = data.get("irs1040_schedule_d", {})
    _add(
        people[0],
        "long_term_capital_gains",
        -schedule_d.get("lt_capital_loss_carryover_input", 0),
    )
    _add(
        people[0],
        "short_term_capital_gains",
        -schedule_d.get("st_capital_loss_carryover_input", 0),
    )


_EXPENSES = [
    "advertising",
    "commissions_fees",
    "contract_labor",
    "depletion",
    "employee_benefit",
    "insurance",
    "mortgage_interest",
    "other_interest",
    "legal_professional",
    "office_expense",
    "pension_psp",
    "machinery_equip_rent",
    "other_rent",
    "repairs_maintenance",
    "supplies",
    "tax_licenses",
    "travel",
    "utilities",
    "wages_expense",
]
_MISC_BOXES = [
    "rents",
    "royalties",
    "other_income",
    "fish_boat_proceeds",
    "medandhlth_care_pmts",
    "subpmts_inlieuof_div_int",
    "crop_ins_proceeds",
    "grsproceeds_pd_to_atty",
    "fish_purch_for_resale",
    "nonqual_deferred_comp",
]


def _businesses(data, people, reasons):
    for business in data.get("irs1040_schedulec", []):
        p = _owner(people, business["who_applies_to"])
        revenue = business.get("gross_receipts_cash", 0) + business.get(
            "other_income", 0
        )
        revenue += sum(r.get("nec_comp", 0) for r in business.get("irs1099_nec", []))
        revenue += sum(r.get("k_comp", 0) for r in business.get("irs1099_k", []))
        revenue += sum(
            r.get(k, 0) for r in business.get("irs1099_misc", []) for k in _MISC_BOXES
        )
        expenses = sum(business.get(k, 0) for k in _EXPENSES)
        expenses += sum(
            r["other_expense_detail_amt"]
            for r in business.get("other_expense_detail", [])
        )
        if (
            business.get("vehicle_info_group")
            or business.get("business_home_area")
            or business.get("meal_entertainment")
        ):
            reasons.add("business: Schedule C vehicle, home office, or meals worksheet")
        profit = revenue - expenses - business.get("returns_allowances", 0)
        sstb = business.get("specified_service", False)
        prefix = "sstb_" if sstb else ""
        _add(p, prefix + "self_employment_income", profit)
        _add(
            p,
            "self_employed_health_insurance_premiums",
            business.get("se_health_insurance", 0),
        )
        _add(
            p,
            prefix + "w2_wages_from_qualified_business",
            business.get("wages_paid", 0),
        )
        _add(
            p,
            prefix + "unadjusted_basis_qualified_property",
            business.get("ubia_qualified_property", 0),
        )
        if (
            business.get("former_employer")
            or not business.get("use_calculated_qbi", True)
            or not business.get("qualified_business", True)
        ):
            reasons.add("QBI: business-specific eligibility or taxpayer adjustment")
    if data.get("irs8995a_schedulec", {}).get("prior_yr_qbi_loss_carryforward"):
        reasons.add("QBI: prior-year loss carryforward")


def _education(data, people):
    for student in data.get("irs8863", {}).get("student_educational_instn_grp", []):
        p = _owner(
            people,
            {"taxpayer_info": "taxpayer", "spouse_info": "spouse"}[student["student"]],
        )
        schools = student["educational_institution_group"]
        p.update(
            qualified_tuition_expenses=sum(
                s.get("qualified_expenses", 0) for s in schools
            ),
            is_pursuing_credential_for_american_opportunity_credit=student[
                "academic_period_eligible_student"
            ],
            is_enrolled_at_least_half_time_for_american_opportunity_credit=student[
                "academic_period_eligible_student"
            ],
            has_completed_first_four_years_of_postsecondary_education=student[
                "post_secondary_education"
            ],
            has_felony_drug_conviction=student["drug_felony_conviction"],
            # The questionnaire asks whether the four-claim limit was reached.
            american_opportunity_credit_claimed_prior_years=4
            if student["prior_year_credit_claimed"]
            else 0,
            has_american_opportunity_credit_1098_t_or_exception=any(
                s.get("current_year_1098t_received") for s in schools
            ),
            has_american_opportunity_credit_institution_ein=any(
                s.get("ein") for s in schools
            ),
            attends_eligible_educational_institution_for_american_opportunity_credit=any(
                s.get("current_year_1098t_received") for s in schools
            ),
            attends_eligible_educational_institution_for_lifetime_learning_credit=any(
                s.get("current_year_1098t_received") for s in schools
            ),
            has_lifetime_learning_credit_1098_t_or_exception=any(
                s.get("current_year_1098t_received") for s in schools
            ),
        )


def add_finances(raw: dict, household: dict) -> list[str]:
    """Add document-based TY24 inputs and return material comparability limits."""
    data = _values(raw["input"]["return_data"])
    people, tax_unit = household["people"], household["tax_unit"]
    reasons = set()
    tax_unit.update(state_withheld_income_tax=0, local_income_tax=0)
    _wages(data, people, tax_unit, reasons)
    _investment(data, people, reasons)
    _businesses(data, people, reasons)
    _education(data, people)

    schedule = data.get("irs1040_schedule1", {})
    for p in people:
        # Alaska residence alone does not establish receipt of its dividend.
        p["ak_permanent_fund_dividend"] = 0
    people[0]["ak_permanent_fund_dividend"] = schedule.get(
        "alaska_permanent_dividend_tp_input", 0
    )
    interest = schedule.get("student_interest", 0)
    if interest and not schedule.get("paid_student_loan_interest"):
        reasons.add("student loan: interest conflicts with payment answer")
    people[0]["student_loan_interest"] = (
        interest if schedule.get("paid_student_loan_interest") else 0
    )
    if people[0]["student_loan_interest"] and (
        data["irs1040"].get("tp_dependent") or data["irs1040"].get("sp_dependent")
    ):
        reasons.add(
            "student loan: interest ownership or dependency eligibility unresolved"
        )
    for prefix, p in zip(
        ("tp", "sp"),
        people[: 2 if data["irs1040"]["filing_status"] == "married_jointly" else 1],
    ):
        amount = schedule.get(prefix + "_educator_exp_amount", 0)
        if amount and not schedule.get("qualified_educator"):
            reasons.add("educator: expense conflicts with eligibility answer")
        if schedule.get("qualified_educator"):
            p["educator_expense"] = amount
    for row in schedule.get("irs1099_g", []):
        p = _owner(people, row["g_who_applies_to"])
        _add(
            p,
            "unemployment_compensation",
            row.get("g_unemployment_comp", 0)
            - row.get("g_amount_repaid_current_year", 0),
        )
        for loc in row.get("irs1099_g_state", []):
            _add(tax_unit, "state_withheld_income_tax", loc.get("g_state_wh", 0))
    for row in data.get("irs1099_r", []):
        p = _owner(people, row["who_applies_to"])
        name = (
            "taxable_ira_distributions"
            if row.get("irasepsimple_ind_input")
            else "taxable_pension_income"
        )
        _add(p, name, row["taxable_amt_input"])
    for row in data.get("ssa_1099", {}).get("ssa_1099_grp", []):
        p = _owner(people, row["ssa_who_applies_to"])
        _add(p, "social_security", row.get("ssa_net_benefits", 0))
        _add(
            p,
            "medical_expense_health_insurance_premiums",
            row.get("ssa_medicare_premiums", 0)
            + row.get("ssa_prescription_drug_premiums", 0),
        )
    care = data.get("irs2441", {})
    tax_unit["tax_unit_childcare_expenses"] = sum(
        r.get("qualifying_expenses_paid", 0)
        for r in care.get("qualifying_person_grp", [])
    )
    if care.get("carryover") or care.get("forfeited"):
        reasons.add("dependent care: prior-year carryover or forfeiture")
    if data.get("irs8962", {}).get("received_1095a"):
        reasons.add("marketplace: advance premium tax credit reconciliation")
    form = data["irs1040"]
    if any(
        form.get(f"estimated_tax_payment_{i}") for i in range(1, 5)
    ) and not form.get("paid_estimated_tax_pmts"):
        reasons.add("estimated payment: amounts conflict with payment answer")
    return sorted(reasons)
