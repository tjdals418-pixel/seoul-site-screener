from __future__ import annotations

import re

import pandas as pd

# openpyxl rejects these control chars
_ILLEGAL = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")


def strip_illegal_chars(value):
    if isinstance(value, str):
        return _ILLEGAL.sub("", value)
    return value


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(strip_illegal_chars)
