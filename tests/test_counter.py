import math

import pytest

from app.counter import count_reps, joint_angle, median_smooth
from app.exercises import EXERCISES

SQUAT = EXERCISES["squat"]


def signal(*segments, fps=10):
    """Piecewise-linear angle signal: segments of (from, to, seconds)."""
    angles = []
    for a, b, secs in segments:
        n = int(secs * fps)
        angles += [a + (b - a) * i / n for i in range(n)]
    return [i / fps for i in range(len(angles))], angles


def test_joint_angle():
    assert joint_angle((0, 1), (0, 0), (1, 0)) == pytest.approx(90)
    assert joint_angle((0, 1), (0, 0), (0, -1)) == pytest.approx(180)
    assert math.isnan(joint_angle((0, 0), (0, 0), (1, 0)))


def test_one_rep():
    t, a = signal((175, 175, 0.5), (175, 80, 0.8), (80, 175, 0.8), (175, 175, 0.5))
    reps = count_reps(t, a, SQUAT)
    assert len(reps) == 1
    assert reps[0].min_angle < 100


def test_three_reps():
    rep = [(175, 85, 0.7), (85, 175, 0.7)]
    t, a = signal((175, 175, 0.3), *rep * 3, (175, 175, 0.3))
    assert len(count_reps(t, a, SQUAT)) == 3


def test_shallow_movement_not_counted():
    t, a = signal((175, 175, 0.3), (175, 130, 0.7), (130, 175, 0.7), (175, 175, 0.3))
    assert count_reps(t, a, SQUAT) == []


def test_noise_around_threshold_is_one_rep():
    t, a = signal((175, 175, 0.3), (175, 80, 0.8), (80, 175, 0.8), (175, 175, 0.3))
    a[12] = 170  # single-frame spike while down: removed by median filter
    assert len(count_reps(t, a, SQUAT)) == 1


def test_video_starting_mid_rep_does_not_count_half_rep():
    t, a = signal((90, 175, 0.8), (175, 175, 0.5))
    assert count_reps(t, a, SQUAT) == []


def test_too_fast_rep_filtered():
    t, a = signal((175, 175, 0.3), (175, 80, 0.1), (80, 175, 0.1), (175, 175, 0.3), fps=30)
    assert count_reps(t, a, SQUAT) == []


def test_median_smooth_keeps_length():
    assert len(median_smooth([1, 2, 3, 100, 5, 6], 5)) == 6
