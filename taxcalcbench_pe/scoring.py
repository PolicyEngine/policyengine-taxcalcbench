"""Classify one amount in a synthetic TY24 case."""

from decimal import ROUND_HALF_UP, Decimal
from math import isfinite


def compare_amount(
    reference: int | None,
    actual: float | None,
    *,
    unsupported: str | None = None,
    limitations: tuple[str, ...] = (),
) -> dict:
    """Compare whole dollars only when the XML, inputs and model support the line."""
    if actual is not None and not isfinite(actual):
        raise ValueError("Model returned a non-finite amount")
    rounded = (
        None
        if actual is None
        else int(Decimal(str(actual)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    )
    delta = None
    if unsupported:
        status = "unsupported"
    elif reference is None:
        status = "absent_reference"
    elif limitations:
        status = "input_or_key_limitation"
    else:
        if rounded is None:
            raise ValueError("Missing model calculation for a supported line")
        delta = rounded - reference
        status = "exact" if delta == 0 else "different"
    return {
        "reference": reference,
        "model": actual,
        "model_rounded": rounded,
        "difference": delta,
        "status": status,
        "unsupported_reason": unsupported,
        "limitations": list(limitations),
    }
