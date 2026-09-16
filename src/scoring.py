"""RMSE and constant-submission math for the Formula Lab tab.

The coverage-gap formula itself is no longer guessed -- it's computed directly from the
challenge's public data by src/pipeline.py, following the exact method documented in the
bucket's own README. These helpers are for cross-checking your public-leaderboard RMSE
against expectations, not for reverse-engineering an unknown formula.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def rmse(a: pd.Series, b: pd.Series) -> float:
    a, b = a.align(b, join="inner")
    return float(np.sqrt(np.mean((a.values - b.values) ** 2)))


def constant_submission_solve(c1: float, r1: float, c2: float, r2: float) -> tuple[float, float]:
    """Given two constant submissions c1,c2 and their returned RMSE r1,r2 against the hidden
    reference, solve RMSE^2 = variance + (mean-c)^2 for (mean, variance) of the reference scores.
    """
    if c2 == c1:
        raise ValueError("c1 and c2 must differ")
    mean = (r1**2 - r2**2 - c1**2 + c2**2) / (2 * (c2 - c1))
    variance = r1**2 - (mean - c1) ** 2
    return mean, variance


def expected_rmse_for_constant(c: float, mean: float, variance: float) -> float:
    return float(np.sqrt(variance + (mean - c) ** 2))
