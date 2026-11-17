"""Toy models on synthetic data. The numbers mean nothing outside this demo."""

import math
import random


def make_data(seed, n):
    """Synthetic points: y = 2x + 1 + noise. Not real data."""
    rng = random.Random(seed)
    xs = [rng.uniform(0, 10) for _ in range(n)]
    ys = [2.0 * x + 1.0 + rng.gauss(0, 1.0) for x in xs]
    return xs, ys


def fit_mean(xs, ys):
    mean = sum(ys) / len(ys)
    return lambda x: mean


def fit_line(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    return lambda x: slope * x + intercept


def rmse(model, xs, ys):
    err = [(model(x) - y) ** 2 for x, y in zip(xs, ys)]
    return math.sqrt(sum(err) / len(err))
