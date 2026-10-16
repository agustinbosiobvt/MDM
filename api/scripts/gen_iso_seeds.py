"""Regenerate alembic/seed/{countries,currencies}.csv from pycountry (dev-only dependency).

The CSVs are committed so migrations are reproducible without pycountry.
Usage: uv run python scripts/gen_iso_seeds.py
"""

import csv
from pathlib import Path

import pycountry

SEED_DIR = Path(__file__).resolve().parents[1] / "alembic" / "seed"

# ISO 4217 codes that are not trade currencies (funds, metals, testing, SDR...).
NON_TRADE = {
    "BOV",
    "CHE",
    "CHW",
    "CLF",
    "COU",
    "MXV",
    "USN",
    "UYI",
    "UYW",
    "XAG",
    "XAU",
    "XBA",
    "XBB",
    "XBC",
    "XBD",
    "XDR",
    "XPD",
    "XPT",
    "XSU",
    "XTS",
    "XUA",
    "XXX",
    "VED",
}
# ISO 4217 minor units; everything else has 2.
MINOR_UNITS = {
    **dict.fromkeys(
        [
            "BIF",
            "CLP",
            "DJF",
            "GNF",
            "ISK",
            "JPY",
            "KMF",
            "KRW",
            "PYG",
            "RWF",
            "UGX",
            "VND",
            "VUV",
            "XAF",
            "XOF",
            "XPF",
        ],
        0,
    ),
    **dict.fromkeys(["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"], 3),
}


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with (SEED_DIR / "countries.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["code", "name"])
        for c in sorted(pycountry.countries, key=lambda c: c.alpha_2):
            w.writerow([c.alpha_2, getattr(c, "common_name", None) or c.name])
    with (SEED_DIR / "currencies.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["code", "name", "minor_units"])
        for cur in sorted(pycountry.currencies, key=lambda c: c.alpha_3):
            if cur.alpha_3 not in NON_TRADE:
                w.writerow([cur.alpha_3, cur.name, MINOR_UNITS.get(cur.alpha_3, 2)])


if __name__ == "__main__":
    main()
