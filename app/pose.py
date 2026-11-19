"""Video frames -> per-frame joint angle using MediaPipe Pose Landmarker (Tasks API)."""

from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (PoseLandmarker, PoseLandmarkerOptions,
                                           RunningMode)

from app.counter import joint_angle
from app.exercises import Exercise

LANDMARKS = {
    "left": {"shoulder": 11, "elbow": 13, "wrist": 15, "hip": 23, "knee": 25, "ankle": 27},
    "right": {"shoulder": 12, "elbow": 14, "wrist": 16, "hip": 24, "knee": 26, "ankle": 28},
}
MIN_VISIBILITY = 0.5


@dataclass(frozen=True)
class AngleSeries:
    times: list[float]
    angles: list[float]
    frames_sampled: int
    sample_fps: float


def extract_angles(video: Path, ex: Exercise, model_path: Path,
                   sample_fps: float) -> AngleSeries:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError("cannot open video")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / sample_fps))

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,  # MVP: most prominent person only
    )
    times: list[float] = []
    angles: list[float] = []
    sampled = 0
    idx = 0
    try:
        with PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % step == 0:
                    sampled += 1
                    t = idx / src_fps
                    a = _frame_angle(landmarker, frame, int(t * 1000), ex)
                    if a is not None:
                        times.append(round(t, 3))
                        angles.append(a)
                idx += 1
    finally:
        cap.release()
    return AngleSeries(times, angles, sampled, src_fps / step)


def _frame_angle(landmarker: PoseLandmarker, frame, ts_ms: int,
                 ex: Exercise) -> float | None:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = landmarker.detect_for_video(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts_ms)
    if not result.pose_world_landmarks:
        return None
    # World landmarks are 3D (metres, hip-centred): the angle stays correct when the
    # person faces the camera and the bend goes towards it. Visibility comes from
    # the image landmarks.
    world = result.pose_world_landmarks[0]
    image = result.pose_landmarks[0]

    side_angles = []
    for side in LANDMARKS.values():
        ids = [side[j] for j in ex.joints]
        if min(image[i].visibility or 0.0 for i in ids) < MIN_VISIBILITY:
            continue
        a, b, c = ((world[i].x, world[i].y, world[i].z) for i in ids)
        side_angles.append(joint_angle(a, b, c))
    if not side_angles:
        return None
    return min(side_angles) if ex.combine == "min" else sum(side_angles) / len(side_angles)
