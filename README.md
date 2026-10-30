# ProcessFlow — Configurable Event Log Engineering

**Python · pandas · Streamlit · process mining · data quality**

ProcessFlow turns operational CSV/Excel records from multiple systems into standardized event logs for process analysis. Users configure case identifiers, activity/timestamp rules, retained attributes and privacy handling; the engine produces auditable event logs, reconciliation reports, quality checks and descriptive process metrics.

> **Portfolio demonstration:** All bundled order-fulfillment records are fictional and deterministically generated. The application is a generalized adaptation of a previously developed private tool; no real organizational datasets are included in this release candidate.

## Demonstration at a glance

| Scenario | Cases | Events | Activities | Sources | Quality gate |
| --- | ---: | ---: | ---: | ---: | --- |
| Clean order fulfillment | 1,000 | 7,716 | 10 | 4 | **PASS** |
| Two deliberately invalid payment timestamps | 1,000 | 7,714 | 10 | 4 | **FAIL** |

Both runs use fictional **Orders**, **Payments**, **Warehouse**, and **Shipping** sources. The synthetic data includes cancellations, payment retries, repeated quality checks and incomplete shipments; these are business-process variations, not necessarily defects. The invalid scenario contains two *technical* timestamp defects, reported separately by the quality gate.

## Features

- Configurable multi-source CSV/Excel ingestion and event construction (including multiple rules per source)
- Activity normalization and mapping, pseudonymization, and locally stored identity lookups
- Incremental integration, duplicate review, activity multiplicity discovery and configurable resolution
- Reconciliation and validation with **PASS / WARN / FAIL** quality gates and audit artifacts
- Descriptive analytics: process variants, activity coverage, case duration and quality signals
- Streamlit wizard for source upload, privacy choices, event mapping, execution and analysis

## Quick start

Requires Python 3.10+ (tested with the environment available for this release). In Terminal, **enter the extracted repository folder first**:

```bash
cd /path/to/ProcessFlow_GitHub_Release_Candidate
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python run_pipeline.py config/enterprise_orders_clean.yaml
python run_pipeline.py config/enterprise_orders_invalid.yaml
python -m streamlit run ui/app.py
```

On Windows, activate with `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

**Expected validation:** 34 automated tests pass; the clean run returns PASS and the intentionally corrupted run returns FAIL. The invalid scenario may produce a pandas timestamp-format warning. Generated `output/` and `secure_local/` directories are local artifacts and are excluded from version control.

## Using the Streamlit app

1. Upload the four CSV files under `examples/enterprise_orders/` as **raw source data**.
2. Configure privacy: treat `Order ID` consistently as a pseudonymized case identifier across sources. Do not preserve identifying source columns unnecessarily.
3. For each source, use `Order ID` as the case identifier and select its activity/timestamp fields from the table below.
4. Run validation and inspect the Results and Analysis tabs.
5. For the negative test, replace **only** `payments.csv` with `payments_invalid_demo.csv` in a new run.

| Source | Activity field | Timestamp field |
| --- | --- | --- |
| `orders.csv` | `Status` | `Event Time` |
| `payments.csv` | `Payment Status` | `Payment Time` |
| `warehouse.csv` | `Warehouse Activity` | `Warehouse Time` |
| `shipping.csv` | `Shipping Status` | `Shipping Time` |

For step-by-step guidance see [Enterprise Demo Guide](ENTERPRISE_DEMO_GUIDE.md).

## Repository layout

```text
config/                         YAML examples for CLI execution
examples/                       Fictional datasets
pipeline/                       Event engineering, privacy, QA and analytics engine
scripts/generate_enterprise_demo.py  Deterministic synthetic data generator
tests/                          Automated regression tests
ui/app.py                       Streamlit application
run_pipeline.py                 Command-line entry point
```

## Architecture

```text
CSV / Excel sources
      ↓
Source configuration + privacy classification
      ↓
Activity mapping + event-rule generation
      ↓
Case identity continuity + multi-source integration
      ↓
Reconciliation + timestamp/duplicate/temporal validation
      ↓
Quality gate + standardized event log + audit package
      ↓
Process variants, coverage, duration and descriptive analysis
```

## Privacy, limitations and release status

This application is intended for local analysis of **synthetic or authorized datasets**. Pseudonymization is not anonymization: local identity lookup files and generated outputs must remain protected. Review all exports before sharing. Synthetic data is not evidence of real-world business performance, and PASS means the *configured checks* passed—not that the underlying data is complete or unbiased.

This ZIP is a **release candidate**, not an uploaded GitHub repository. Automated scans cannot guarantee the absence of confidential material or resolve software publication rights. Complete the [Publication Checklist](PUBLICATION_CHECKLIST.md) and obtain any necessary permissions before making it public. A license has deliberately not been assigned; choose one only after confirming your rights to license the code.
