# Retail Data Pipeline

Turns the Online Retail II Excel workbook (UCI, 1.07M sales lines, 2009–2011) into
typed, analysis-ready data.

## Setup
1. Download the dataset from https://archive.ics.uci.edu/dataset/502/online+retail+ii
   and place `online_retail_II.xlsx` in `data/`.
2. `python -m venv .venv`, activate it, then `pip install -r requirements.txt`.

## Steps
| Script | Reads | Writes |
| --- | --- | --- |
| `scripts/prepare_raw_data.py` | `data/online_retail_II.xlsx` | `data/online_retail_II_prepared.parquet`, `.xlsx` |

`notebooks/01_raw_data_prep.ipynb` shows the investigation behind each preparation step.