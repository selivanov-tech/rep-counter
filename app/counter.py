"""Pure rep-counting logic: angle signal -> smoothed -> hysteresis state machine."""

import math
from dataclasses import dataclass

import numpy as np

from app.exercises import STANCE_SPLIT_DEG, Exercise

Point = tuple[float, ...]  # 2D or 3D


def joint_angle(a: Point, b: Point, c: Point) -> float:
    """Angle ABC in degrees (at vertex b), for 2D or 3D points."""
    v1 = [x - y for x, y in zip(a, b)]
    v2 = [x - y for x, y in zip(c, b)]
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return float("nan")
    cos = sum(x * y for x, y in zip(v1, v2)) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def median_smooth(values: list[float], window: int = 5) -> list[float]:
    if window <= 1 or len(values) < 3:
        return list(values)
    half = window // 2
    arr = np.asarray(values, dtype=float)
    return [float(np.median(arr[max(0, i - half): i + half + 1])) for i in range(len(arr))]


@dataclass(frozen=True)
class Rep:
    start_s: float
    bottom_s: float
    end_s: float
    min_angle: float
    hip_asym: float | None = None


def count_reps(times: list[float], angles: list[float], ex: Exercise,
               smooth_window: int = 5) -> list[Rep]:
    """Count UP -> DOWN -> UP cycles. Counting starts only after the first UP is seen,
    so a video that begins mid-rep does not produce a half rep."""
    if len(times) != len(angles):
        raise ValueError("times and angles must have equal length")
    signal = median_smooth(angles, smooth_window)

    reps: list[Rep] = []
    state: str | None = None
    start = bottom_t = 0.0
    bottom_a = math.inf
    for t, a in zip(times, signal):
        if state is None:
            if a > ex.up:
                state = "UP"
        elif state == "UP":
            if a < ex.down:
                state, start, bottom_t, bottom_a = "DOWN", t, t, a
        else:  # DOWN
            if a < bottom_a:
                bottom_t, bottom_a = t, a
            if a > ex.up:
                state = "UP"
                if t - start >= ex.min_rep_s:
                    reps.append(Rep(round(start, 2), round(bottom_t, 2), round(t, 2),
                                    round(bottom_a, 1)))
    return reps


@dataclass(frozen=True)
class RejectedRep:
    rep: Rep
    reason: str


def check_stance(reps: list[Rep], times: list[float], hip_asym: list[float],
                 ex: Exercise, window: int = 2) -> tuple[list[Rep], list[RejectedRep]]:
    """Split reps into accepted and rejected by the stance at the bottom.
    The knee angle alone cannot tell a squat from a lunge, the hip asymmetry can."""
    if len(times) != len(hip_asym):
        raise ValueError("times and hip_asym must have equal length")
    accepted: list[Rep] = []
    rejected: list[RejectedRep] = []
    for rep in reps:
        i = min(range(len(times)), key=lambda k: abs(times[k] - rep.bottom_s))
        asym = round(float(np.median(hip_asym[max(0, i - window): i + window + 1])), 1)
        rep = Rep(rep.start_s, rep.bottom_s, rep.end_s, rep.min_angle, asym)
        split = asym >= STANCE_SPLIT_DEG
        if ex.stance == "symmetric" and split:
            rejected.append(RejectedRep(rep, f"stance looks split (lunge-like), {ex.name} expected"))
        elif ex.stance == "split" and not split:
            rejected.append(RejectedRep(rep, f"stance looks symmetric (squat-like), {ex.name} expected"))
        else:
            accepted.append(rep)
    return accepted, rejected
