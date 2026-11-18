"""Request federal outputs for a one-person return through the pinned US bundle."""

import policyengine as pe
from microdf import MicroDataFrame
from policyengine.core import Simulation
from policyengine.tax_benefit_models.common import (
    EntityResult,
    HouseholdResult,
    dispatch_extra_variables,
)
from policyengine.utils.household_validation import validate_household_input


def calculate_federal_outputs(
    household: dict, extra_variables: list[str]
) -> HouseholdResult:
    """Calculate only the requested outputs, without deriving SPM poverty.

    The bundle's household API always includes SPM poverty measurements. A
    youth filing a return supplies too few household facts for those measures.
    An in-memory one-record dataset lets the same model calculate federal tax
    outputs without supplying a fictitious adult or an independence election.
    """
    if len(household["people"]) != 1 or household["marital_unit"] != [{"members": [0]}]:
        raise ValueError("The one-record federal calculation requires a single filer")
    model = pe.us.model
    requested = dispatch_extra_variables(model_version=model, names=extra_variables)
    # Singleton groups represent the return's own roster in the entity tables.
    memberships = {
        f"{entity}_id": 1 for entity in model.entity_variables if entity != "person"
    }
    inputs = {
        "person": household["people"][0],
        "tax_unit": household["tax_unit"],
        "household": household["household"],
    }
    validate_household_input(
        model_version=model,
        entities={entity: [record] for entity, record in inputs.items()},
    )
    inputs["person"] = {**inputs["person"], **memberships}
    tables = {}
    for entity in model.entity_variables:
        weight = f"{entity}_weight"
        row = {f"{entity}_id": 1, weight: 1, **inputs.get(entity, {})}
        tables[entity] = MicroDataFrame([row], weights=weight)
    dataset = pe.us.PolicyEngineUSDataset(
        name="TaxCalcBench",
        description="One synthetic federal tax return",
        year=household["year"],
        data=pe.us.USYearData(**tables),
    )
    simulation = Simulation(
        dataset=dataset,
        tax_benefit_model_version=model.model_copy(
            update={"entity_variables": requested}
        ),
        spm=household["spm"],
    )
    simulation.run()
    result = HouseholdResult()
    for entity, names in requested.items():
        table = getattr(simulation.output_dataset.data, entity)
        record = EntityResult({name: table[name].iloc[0] for name in names})
        result[entity] = [record] if entity == "person" else record
    return result
