"""Exercise registry. Adding an exercise = adding an entry here; the counter is generic."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Exercise:
    name: str
    title: str
    joints: tuple[str, str, str]  # angle is measured at the middle joint
    down: float  # angle below this -> DOWN
    up: float  # angle above this -> UP
    min_rep_s: float = 0.4
    combine: Literal["mean", "min"] = "mean"  # how to merge left/right sides


EXERCISES: dict[str, Exercise] = {
    e.name: e
    for e in (
        # Angles are 3D (MediaPipe world landmarks). A straight leg reads ~160°, not 180°,
        # so UP thresholds sit around 145°. Squat values verified on tests/data/squat_1.mp4
        # (standing ~160°, bottom ~65°); push-up and lunge values are unverified guesses.
        Exercise("squat", "Squat", ("hip", "knee", "ankle"), down=110, up=145),
        Exercise("pushup", "Push-up", ("shoulder", "elbow", "wrist"), down=90, up=145),
        Exercise("lunge", "Lunge", ("hip", "knee", "ankle"), down=105, up=145,
                 min_rep_s=0.5, combine="min"),
    )
}
