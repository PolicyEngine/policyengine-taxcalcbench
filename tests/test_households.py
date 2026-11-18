"""Source-only fixtures exercise household identity and eligibility boundaries."""

from hypothesis import given
from hypothesis import strategies as st

from taxcalcbench_pe.households import (
    CLAIM,
    RESIDENCY,
    UNCLAIMED,
    affected_by_limitation,
    build_household,
    limitations,
)


def fields(**values):
    return {name: {"value": value} for name, value in values.items()}


def questionnaire(status: str, dependent_birth_years: list[int]) -> dict:
    form = fields(
        filing_status=status,
        tp_date_of_birth="1980-10-31",
        tp_student=False,
        tp_blind=False,
        tp_dependent=False,
        sp_date_of_birth="1970-05-11",
        sp_student=False,
        sp_blind=True,
        sp_dependent=False,
    )
    form["dependent_detail"] = [
        fields(
            dependent_date_of_birth=f"{year}/01/01",
            dependent_disabled=False,
            dependent_student_for_5_plus_months=True,
            dependent_supported_by_tp=True,
            dependent_us_citizen_national_or_resident_alien=True,
        )
        for year in dependent_birth_years
    ]
    return {
        "input": {
            "return_header": fields(state="VT", zip_code="05001"),
            "return_data": {"irs1040": form},
        }
    }


@given(
    status=st.sampled_from(["single", "head_of_household", "married_jointly"]),
    birth_years=st.lists(st.integers(1930, 2024), max_size=8),
)
def test_return_members_and_marital_units(status, birth_years):
    """Changing ages never changes filer identity or assigns an older parent as spouse."""
    result = build_household(questionnaire(status, birth_years))
    people = result["people"]
    first_dependent = 2 if status == "married_jointly" else 1
    assert len(people) == first_dependent + len(birth_years)
    assert [p["is_tax_unit_head"] for p in people] == [True] + [False] * (
        len(people) - 1
    )
    assert [i for i, p in enumerate(people) if p["is_tax_unit_spouse"]] == (
        [1] if status == "married_jointly" else []
    )
    assert [p["is_tax_unit_dependent"] for p in people] == (
        [False] * first_dependent + [True] * len(birth_years)
    )
    assert [p["age"] for p in people[first_dependent:]] == [
        2024 - y for y in birth_years
    ]
    assert all(p["is_full_time_student"] for p in people[first_dependent:])
    assert [g["members"] for g in result["marital_unit"]] == [
        list(range(first_dependent)),
        *[[i] for i in range(first_dependent, len(people))],
    ]
    assert result["household"] == {"state_code": "VT", "zip_code": "05001"}


def test_dependency_eligibility_and_actual_claim_are_distinct():
    raw = questionnaire("married_jointly", [])
    raw["input"]["return_data"]["irs1040"]["sp_dependent"]["value"] = True
    result = build_household(raw)
    assert result["tax_unit"]["spouse_is_dependent_elsewhere"]
    assert not result["people"][1]["is_tax_unit_dependent"]
    assert result["people"][1]["is_blind"]
    assert "claimed_as_dependent_on_another_return" not in result["people"][1]
    assert limitations(raw) == [CLAIM]


def test_hoh_qualifying_person_is_not_an_imputed_dependent():
    raw = questionnaire("head_of_household", [])
    form = raw["input"]["return_data"]["irs1040"]
    form.update(fields(hoh_planning_to_claim_child_or_dependent_credit=False))
    assert len(build_household(raw)["people"]) == 1
    assert limitations(raw) == [UNCLAIMED]
    assert affected_by_limitation("27", UNCLAIMED)
    assert not affected_by_limitation("1a", UNCLAIMED)


def test_uncertain_residency_keeps_listed_person_and_marks_affected_lines():
    raw = questionnaire("married_jointly", [2003])
    dep = raw["input"]["return_data"]["irs1040"]["dependent_detail"][0]
    dep["dependent_us_citizen_national_or_resident_alien"]["value"] = False
    assert build_household(raw)["people"][2]["is_tax_unit_dependent"]
    assert limitations(raw) == [RESIDENCY]
    assert affected_by_limitation("19", RESIDENCY)
