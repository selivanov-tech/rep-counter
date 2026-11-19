"""Use case: video file -> count result. Kept free of HTTP concerns."""

from pathlib import Path

from app.counter import check_stance, count_reps
from app.exercises import STANCE_SPLIT_DEG, Exercise
from app.ingest import probe
from app.pose import extract_angles
from app.settings import Settings


def count_video(video: Path, ex: Exercise, settings: Settings) -> dict:
    duration = probe(video, settings.max_duration_s)
    series = extract_angles(video, ex, settings.pose_model_path, settings.sample_fps)
    candidates = count_reps(series.times, series.angles, ex)
    reps, rejected = check_stance(candidates, series.times, series.hip_asym, ex)
    return {
        "exercise": ex.name,
        "count": len(reps),
        "duration_s": round(duration, 2),
        "reps": [r.__dict__ for r in reps],
        "rejected": [{**r.rep.__dict__, "reason": r.reason} for r in rejected],
        "debug": {
            "fps_sampled": round(series.sample_fps, 2),
            "frames_sampled": series.frames_sampled,
            "frames_with_pose": len(series.times),
            "thresholds": {"down": ex.down, "up": ex.up, "stance": ex.stance,
                           "split_deg": STANCE_SPLIT_DEG},
            "angles": [{"t": t, "a": round(a, 1), "h": round(h, 1)}
                       for t, a, h in zip(series.times, series.angles, series.hip_asym)],
        },
    }
