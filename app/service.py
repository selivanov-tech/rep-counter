"""Use case: video file -> count result. Kept free of HTTP concerns."""

from pathlib import Path

from app.counter import count_reps
from app.exercises import Exercise
from app.ingest import probe
from app.pose import extract_angles
from app.settings import Settings


def count_video(video: Path, ex: Exercise, settings: Settings) -> dict:
    duration = probe(video, settings.max_duration_s)
    series = extract_angles(video, ex, settings.pose_model_path, settings.sample_fps)
    reps = count_reps(series.times, series.angles, ex)
    return {
        "exercise": ex.name,
        "count": len(reps),
        "duration_s": round(duration, 2),
        "reps": [r.__dict__ for r in reps],
        "debug": {
            "fps_sampled": round(series.sample_fps, 2),
            "frames_sampled": series.frames_sampled,
            "frames_with_pose": len(series.times),
            "thresholds": {"down": ex.down, "up": ex.up},
            "angles": [{"t": t, "a": round(a, 1)}
                       for t, a in zip(series.times, series.angles)],
        },
    }
