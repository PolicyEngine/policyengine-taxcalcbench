# PolicyEngine US × TaxCalcBench

Run PolicyEngine US on the 51 synthetic federal returns in Column Tax’s 2024 TaxCalcBench dataset and compare individual Form 1040 lines with the supplied e-file XML. The comparison covers selected filing situations. Each case has equal standing and carries no population weight.

## Run the comparison

Install [uv](https://docs.astral.sh/uv/), then run these commands from the repository root:

```sh
uv sync --frozen --python 3.13
bash scripts/fetch-ty24.sh
uv run python -m taxcalcbench_pe
```

The runner verifies both source files for every case against [the checksum manifest](taxcalcbench_pe/ty24_manifest.json). It prints counts by line and writes the case-level results to `results/ty24.json`. Use `--fixtures PATH` for an existing TY24 dataset checkout and `--out PATH` to choose the report location. The report includes the TaxCalcBench commit and installed PolicyEngine package versions.

## Compare five starter cases

Run `uv run python -m taxcalcbench_pe --curated` for a smaller set that two engines can compare by hand. The [case list](taxcalcbench_pe/curated.json) pairs each return with a question, the relevant Form 1040 lines and the 2024 IRS instructions. It covers wages plus unemployment, an older couple’s standard deduction, the IRS tax table, the excess business loss limit and a stock sale with conflicting holding-period information. The runner writes all 19 line results for each case to `results/ty24-curated.json`. The full 51-case suite remains the default.

## Read the results

Each row identifies a case and a Form 1040 line, the reference amount when present, the model amount, its rounded value, and any limitations. The status describes how to interpret that row.

| Status | Meaning |
| --- | --- |
| `exact` | The model matches the explicit XML amount after rounding to the nearest whole dollar, with half dollars rounded away from zero. |
| `different` | The rounded model amount differs. The signed difference equals model minus reference. |
| `input_or_key_limitation` | An unresolved input, unsupported treatment, or conflicting source answer affects a line with an explicit reference. |
| `absent_reference` | The reference XML omits a mapped line. The report flags eligible nonzero model amounts in the summary and preserves any input limitations on each row. |
| `unsupported` | The adapter lacks a complete PolicyEngine equivalent for this line. |

[Column Tax’s TY24 evaluator](https://github.com/column-tax/tax-calc-bench/blob/fdfe0db992ae9033f5b8b942633181a3596da64c/tax_calc_bench/tax_return_evaluator.py) treats an omitted XML element as zero and grades all 19 targets. This comparison reports all 19 and scores the supported lines with explicit reference values and sufficiently specified inputs. For example, the adapter compares adjusted gross income (line 11). It leaves the amount owed (line 37) outside the scored set because a complete reconciliation would also require withholding and payments. Use the per-line counts alongside any match rate.

## Trace a difference

[Households](taxcalcbench_pe/households.py) and [finances](taxcalcbench_pe/finances.py) translate the questionnaire into model inputs. The [line definitions](taxcalcbench_pe/lines.py) identify the PolicyEngine variables and the corresponding Form 1040 XML element. The runner computes the return before reading its XML. Case names identify documented upstream issues when grading. They never determine a model input.

For a difference, inspect the questionnaire and adapter, trace the first differing line, then check the 2024 form instructions. A later line can inherit an earlier difference. Model scope, elections, filing-table conventions and reference errors can all affect a comparison. The [upstream issue on contradictory answers](https://github.com/column-tax/tax-calc-bench/issues/161) and [missing marketplace data](https://github.com/column-tax/tax-calc-bench/issues/66) describe two examples.

The locked PolicyEngine 6.20.2 bundle runs the US model at 2.2.2. Column Tax supplies the [synthetic cases](https://github.com/column-tax/tax-calc-bench/tree/fdfe0db992ae9033f5b8b942633181a3596da64c/tax_calc_bench/ty24/test_data) under its [MIT license](https://github.com/column-tax/tax-calc-bench/blob/fdfe0db992ae9033f5b8b942633181a3596da64c/LICENSE).

## Development

CI reruns all 51 cases and publishes the JSON report as a workflow artifact. The [regression baseline](taxcalcbench_pe/matched_lines.json) records case IDs and line numbers that matched under the pinned bundle. CI fails if one of those cells changes or drops out of the scored set.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```
