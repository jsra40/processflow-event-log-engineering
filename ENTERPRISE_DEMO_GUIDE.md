# Fictional enterprise order-fulfillment demonstration

All records are generated synthetically. No names, patient data, real organizations, credentials, or operational exports are required.

## Scenario

1,000 fictional orders spanning four independent source systems, each with its own activity and timestamp columns. The dataset contains payment retries, cancellations, repeated quality checks, incomplete deliveries, shipping delays, and multiple sales channels.

| File | Rows | Activity column | Timestamp column |
| --- | ---: | --- | --- |
| `examples/enterprise_orders/orders.csv` | 1,058 | `Status` | `Event Time` |
| `examples/enterprise_orders/payments.csv` | 1,032 | `Payment Status` | `Payment Time` |
| `examples/enterprise_orders/warehouse.csv` | 2,898 | `Warehouse Activity` | `Warehouse Time` |
| `examples/enterprise_orders/shipping.csv` | 2,728 | `Shipping Status` | `Shipping Time` |

All files share `Order ID` as the source case identifier. Configure its privacy action as **Pseudonymize**, targeting `Case_ID`, with a consistent namespace across all four sources. Keep useful nonsensitive attributes such as `Channel`, `Priority`, `Payment Method`, `Facility`, and `Carrier`. Each source needs one event rule with its corresponding activity and timestamp fields. Do not add extra event rules for the first demo.

## Recommended reproducible CLI demonstration

Run from the repository root:

```bash
python -m pytest -q
python run_pipeline.py config/enterprise_orders_clean.yaml
python run_pipeline.py config/enterprise_orders_invalid.yaml
```

Expected results, verified on the packaged example:

- Clean: **1,000 cases**, **7,716 events**, **10 activities**, quality gate **PASS** (23 checks).
- Invalid: **1,000 cases**, **7,714 events**, quality gate **FAIL** (24 checks), with **2 deliberately invalid/missing payment timestamps**.
- The invalid dataset is `payments_invalid_demo.csv`; use it **instead of** `payments.csv` only when demonstrating quality-gate failure.
- Output folders and identity lookups are generated locally and ignored by Git; **do not publish them**.

## Streamlit workflow

Run `python -m streamlit run ui/app.py`. Upload the four clean CSV files together. For each source, classify as raw source data; select `Order ID` as the case identifier; configure privacy pseudonymization consistently; configure the matching activity/timestamp columns; then validate and run. For the defect scenario, replace only the payments source with `payments_invalid_demo.csv` and run as a separate project/output.

## Regeneration

Run `python scripts/generate_enterprise_demo.py` from any working directory. The script uses a fixed random seed for deterministic results.

## Interpretation

Incomplete orders, cancellations, payment retries, and repeated quality checks are legitimate *business-process variations*, not automatically data-quality failures. Missing/unparseable timestamps in the invalid scenario are intentional technical defects. This is a fictional demonstration and does not claim real-world operational performance.

## Publication precautions

This is a generalized adaptation of the private v1.4.2 implementation. Verify publication rights and inspect source code, metadata, dependencies, and configuration before making the repository public. Do not commit generated `output/` or `secure_local/` contents.
