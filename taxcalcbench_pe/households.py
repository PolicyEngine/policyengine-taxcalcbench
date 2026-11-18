"""Map the household facts in a TaxCalcBench TY24 input.json to PolicyEngine."""

from datetime import date

YEAR = 2024
FILING_STATUSES = {
    "single": "SINGLE",
    "married_jointly": "JOINT",
    "head_of_household": "HEAD_OF_HOUSEHOLD",
}
UNCLAIMED = (
    "The head of household lists a qualifying person outside the dependent roster."
)
SUPPORT = "The filer did not supply half the listed dependent's support; the child's own share is unknown."
RESIDENCY = "A listed dependent fails the US citizenship/residency question; Canada/Mexico residence is unspecified."
CLAIM = "A filer can be claimed on another return; the questionnaire does not say whether anyone claimed them."


def _value(group: dict, field: str):
    return group[field]["value"]


def _person(role: str, birth: str) -> dict:
    age = YEAR - date.fromisoformat(birth.replace("/", "-")).year
    if age < 0:
        raise ValueError("A person's birth date follows the tax year")
    return {
        "age": age,
        "is_tax_unit_head": role == "head",
        "is_tax_unit_spouse": role == "spouse",
        "is_tax_unit_dependent": role == "dependent",
    }


def build_household(raw: dict) -> dict:
    """Return one federal filing unit in taxpayer, spouse, dependent-roster order.

    TY24 asks whether *someone can claim* each filer. The model's tax-unit
    dependent-elsewhere inputs proxy this checkbox. The adapter leaves the
    separate person-level *actually claimed* input unspecified.
    """
    data = raw["input"]
    header = data["return_header"]
    form = data["return_data"]["irs1040"]
    status = FILING_STATUSES[_value(form, "filing_status")]
    people = []
    tax_unit = {"filing_status": status}
    filers = [("head", "tp")]
    if status == "JOINT":
        filers.append(("spouse", "sp"))

    for role, prefix in filers:
        person = _person(role, _value(form, f"{prefix}_date_of_birth"))
        person["is_full_time_student"] = _value(form, f"{prefix}_student")
        person["is_blind"] = _value(form, f"{prefix}_blind")
        tax_unit[f"{role}_is_dependent_elsewhere"] = _value(form, f"{prefix}_dependent")
        people.append(person)

    marital_units = [{"members": list(range(len(filers)))}]
    for dep in form.get("dependent_detail", []):
        person = _person("dependent", _value(dep, "dependent_date_of_birth"))
        person["is_full_time_student"] = _value(
            dep, "dependent_student_for_5_plus_months"
        )
        person["is_permanently_and_totally_disabled"] = _value(
            dep, "dependent_disabled"
        )
        marital_units.append({"members": [len(people)]})
        people.append(person)

    return {
        "people": people,
        "marital_unit": marital_units,
        "tax_unit": tax_unit,
        "household": {
            "state_code": _value(header, "state"),
            "zip_code": _value(header, "zip_code"),
        },
        "year": YEAR,
        # The wrapper requests SPM outputs by default. The federal comparison
        # does not use them and TY24 does not identify a county.
        "spm": {"geography_kind": "national"},
    }


def limitations(raw: dict) -> list[str]:
    """Identify ambiguous dependency facts in the unmodified TY24 questionnaire."""
    form = raw["input"]["return_data"]["irs1040"]
    status = _value(form, "filing_status")
    notes = []
    if (
        status == "head_of_household"
        and form.get("hoh_planning_to_claim_child_or_dependent_credit", {}).get("value")
        is False
    ):
        notes.append(UNCLAIMED)
    deps = form.get("dependent_detail", [])
    if any(not _value(dep, "dependent_supported_by_tp") for dep in deps):
        notes.append(SUPPORT)
    if any(
        not _value(dep, "dependent_us_citizen_national_or_resident_alien")
        for dep in deps
    ):
        notes.append(RESIDENCY)
    if _value(form, "tp_dependent") or (
        status == "married_jointly" and _value(form, "sp_dependent")
    ):
        notes.append(CLAIM)
    return notes


def affected_by_limitation(line_number: str, reason: str) -> bool:
    """Conservatively exclude credit amounts and totals sensitive to dependency.

    These memberships use 2024 Form 1040 line labels. For a claimable filer,
    the dependency flag can also affect adjustments (e.g., student-loan
    interest) and both deductions.
    """
    if reason not in (UNCLAIMED, SUPPORT, RESIDENCY, CLAIM):
        return False
    credit_lines = {
        "19",
        "20",
        "21",
        "22",
        "23",
        "24",
        "27",
        "28",
        "29",
        "31",
        "32",
        "33",
        "34",
        "35a",
        "36",
        "37",
    }
    return line_number in credit_lines or (
        reason == CLAIM
        and line_number in {"10", "11", "12", "13", "14", "15", "16", "17", "18"}
    )
