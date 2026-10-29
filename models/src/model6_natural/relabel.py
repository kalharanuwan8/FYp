"""Recompute training labels on an existing windows.csv without re-extracting."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from models.src.features.windows import relabel_dataframe


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument(
        "--windows",
        type=Path,
        default=Path("models/data/processed/model6_natural/windows.csv"),
    )
    args = p.parse_args(argv)
    df = pd.read_csv(args.windows)
    out = relabel_dataframe(df)
    out.to_csv(args.windows, index=False)
    train = out[out["in_train"] == 1]
    print(train.groupby(["subject_id", "y"]).size())
    print(f"wrote {args.windows} in_train={int(train.shape[0])}")


if __name__ == "__main__":
    main()
