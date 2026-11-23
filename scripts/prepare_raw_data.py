"""
prepare_raw_data.py

Prepares the raw Online Retail II workbook: combines its two sheets, renames the
columns and fixes the column types. The only rows removed are the copies created
by the two sheets overlapping in time; no other row or value is changed.
Cleaning (cancellations, missing customers, zero prices, duplicate lines) is a
separate, later step.

Reads:   data/online_retail_II.xlsx
Writes:  data/online_retail_II_prepared.parquet   all rows, typed, fast to reload
         data/online_retail_II_prepared.xlsx      same rows, one sheet per original
                                                  sheet, for viewing and sharing

The investigation behind each step is in notebooks/01_raw_data_prep.ipynb.
In short:
- The sheets overlap: "Year 2009-2010" ends 2010-12-09 20:01 and "Year 2010-2011"
  starts 2010-12-01 08:26, so the rows in between appear in both. They are removed
  from the second sheet only after checking that both copies are identical.
- invoice, stock_code: Excel stores some values as numbers (489434) and some as
  text (C489449, POST). Parquet allows one type per column, so both become text.
- description: mostly text, a few numbers, some missing -> nullable "string".
- customer_id: float only because many rows are missing -> nullable "Int64".

Expected layout (the script's own folder can have any name):
    OnlineII/
        data/online_retail_II.xlsx
        scripts/prepare_raw_data.py
Run from any folder:  python OnlineII/scripts/prepare_raw_data.py
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent  # scripts/ -> OnlineII/
DATA_DIR = PROJECT_DIR / "data"
SOURCE_FILE = DATA_DIR / "online_retail_II.xlsx"
PARQUET_FILE = DATA_DIR / "online_retail_II_prepared.parquet"
EXCEL_FILE = DATA_DIR / "online_retail_II_prepared.xlsx"

# Original Excel header -> snake_case name. The order is also the expected column order.
COLUMN_NAMES = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
}

LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)                        # creates OnlineII/logs/ if missing
LOG_FILE = LOG_DIR / f"{Path(__file__).stem}.log"   # logs/prepare_raw_data.log

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),                                    # still prints to the terminal
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),  # and appends to the file
    ],
)
log = logging.getLogger(Path(__file__).stem)        # names each line "prepare_raw_data"


def check_columns(sheets: dict[str, pd.DataFrame]) -> None:
    """Stop if any sheet's columns differ; pd.concat would otherwise merge them silently."""
    expected = list(COLUMN_NAMES)
    for name, df in sheets.items():
        if list(df.columns) != expected:
            raise ValueError(f"Sheet '{name}' has columns {list(df.columns)}, expected {expected}")


def prepare_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns and give each column one consistent type."""
    df = df.rename(columns=COLUMN_NAMES)
    df["invoice"] = df["invoice"].astype("string")          # mixed numbers and text
    df["stock_code"] = df["stock_code"].astype("string")    # mixed numbers and text
    df["description"] = df["description"].astype("string")  # text, a few numbers, some missing
    df["customer_id"] = df["customer_id"].astype("Int64")   # whole numbers with missing values
    df["invoice_date"] = pd.to_datetime(df["invoice_date"]) # already dates from Excel; errors if not
    return df


def same_rows(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """True if a and b hold exactly the same rows, in any order, duplicates included."""
    columns = list(a.columns)
    a_sorted = a.sort_values(columns).reset_index(drop=True)
    b_sorted = b.sort_values(columns).reset_index(drop=True)
    return a_sorted.equals(b_sorted)


def remove_overlap(earlier: pd.DataFrame, later: pd.DataFrame, later_name: str) -> pd.DataFrame:
    """Drop from `later` the rows that fall in the time window `earlier` already covers."""
    cut = earlier["invoice_date"].max()
    if later["invoice_date"].min() > cut:
        log.info("No overlap before sheet '%s'", later_name)
        return later

    earlier_window = earlier[earlier["invoice_date"] >= later["invoice_date"].min()]
    later_window = later[later["invoice_date"] <= cut]
    if not same_rows(earlier_window, later_window):
        raise ValueError(
            f"Sheet '{later_name}' overlaps the previous sheet up to {cut}, but the overlapping "
            f"rows differ ({len(earlier_window)} vs {len(later_window)}). Inspect before removing."
        )

    log.info("Sheet '%s' repeats %d rows up to %s; removed them", later_name, len(later_window), cut)
    return later[later["invoice_date"] > cut]


def main() -> None:
    log.info("===== run started =====")
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {SOURCE_FILE}")

    log.info("Reading all sheets of %s (a minute or more)", SOURCE_FILE.name)
    sheets = pd.read_excel(SOURCE_FILE, sheet_name=None)  # None = every sheet, as {name: DataFrame}
    check_columns(sheets)

    prepared = {}
    previous = None
    for name, df in sheets.items():  # sheets are in time order
        df = prepare_sheet(df)
        log.info("Sheet '%s': %d rows, %s to %s", name, len(df), df["invoice_date"].min(), df["invoice_date"].max())
        if previous is not None:
            df = remove_overlap(previous, df, name)
        prepared[name] = df
        previous = df

    combined = pd.concat(prepared.values(), ignore_index=True)
    log.info("Combined: %d rows, %d columns", *combined.shape)
    log.info("Column types:\n%s", combined.dtypes.to_string())
    log.info("Missing values per column:\n%s", combined.isna().sum().to_string())
    log.info("Exact duplicate rows (kept for the cleaning step): %d", combined.duplicated().sum())

    combined.to_parquet(PARQUET_FILE, index=False)
    log.info("Wrote %s", PARQUET_FILE.name)

    log.info("Writing %s (several minutes)", EXCEL_FILE.name)
    with pd.ExcelWriter(EXCEL_FILE) as writer:
        for name, df in prepared.items():
            df.to_excel(writer, sheet_name=name, index=False)
    log.info("Wrote %s", EXCEL_FILE.name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Run failed")   # writes the full error traceback into the log
        raise                         # still stops the script with the error, as before