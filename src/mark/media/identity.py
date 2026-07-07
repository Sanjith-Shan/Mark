"""Identity QC gate — ArcFace face-embedding similarity for character lock.

The #1 requirement for an AI brand ambassador is that the SAME synthetic person
appears in every video, forever. Reference-conditioned generation gets us most
of the way; this module is the *verification* layer: extract frames from a
finished clip, embed each detected face with ArcFace, and compare against the
character's canonical embedding. Drift below a threshold is logged (and, upstream,
can trigger a regenerate).

Design constraints (docs/design/CONTENT-TEMPLATES-BUILD.md, decision 6 + the
AI-influencer research report):

  * EMBEDDINGS ONLY. We use InsightFace's ``buffalo_l`` recognition model to
    compute face embeddings. We NEVER touch its ``inswapper`` face-SWAP model —
    that model is licensed non-commercial research only and face-swap is banned
    from the commercial path. This module cannot swap faces; it only measures.
  * OPTIONAL DEPENDENCY. ``insightface`` + ``onnxruntime`` are NOT installed by
    default. Every function lazy-imports and degrades gracefully to a no-op that
    NEVER blocks the pipeline: with the library absent, :func:`check_frames`
    returns ``{"passed": True, "skipped": True}`` so offline / un-provisioned
    machines render exactly as before. Installing insightface turns the gate on.

To enable the gate:  ``pip install insightface onnxruntime`` (see pyproject
``[project.optional-dependencies] identity`` — an INTEGRATION note, added
centrally, not here).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("mark.identity")

# Cosine-similarity acceptance threshold. ArcFace same-identity pairs typically
# score 0.5-0.8; different identities cluster below ~0.3. 0.45 is a deliberately
# permissive default (generation drift on profile angles / lighting is real) —
# tune on an accepted/rejected set per character.
DEFAULT_THRESHOLD = 0.45

_FACE_APP = None            # cached FaceAnalysis instance (loads models once)
_FACE_APP_TRIED = False     # so we only pay the import/model-load cost once


# --------------------------------------------------------------------------- #
# InsightFace access (lazy, cached, optional)
# --------------------------------------------------------------------------- #
def available() -> bool:
    """True when the ArcFace gate can actually run (insightface importable and
    a model bundle loaded). Cheap after the first call."""
    return _face_app() is not None


def _face_app():
    """Return a cached ``insightface`` FaceAnalysis (buffalo_l), or None when the
    optional dependency is missing / fails to initialise. Never raises."""
    global _FACE_APP, _FACE_APP_TRIED
    if _FACE_APP is not None or _FACE_APP_TRIED:
        return _FACE_APP
    _FACE_APP_TRIED = True
    try:
        from insightface.app import FaceAnalysis  # type: ignore
    except Exception as exc:  # not installed — the common, expected case
        log.info("insightface not available — identity QC gate disabled (%s). "
                 "Install `insightface onnxruntime` to enable face-lock QC.", exc)
        return None
    try:
        app = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"])
        app.prepare(ctx_id=-1, det_size=(640, 640))  # ctx_id=-1 → CPU
        _FACE_APP = app
        log.info("insightface buffalo_l loaded — identity QC gate active.")
    except Exception as exc:
        log.warning("insightface present but failed to initialise (%s) — gate disabled.", exc)
        _FACE_APP = None
    return _FACE_APP


# --------------------------------------------------------------------------- #
# Embeddings + similarity
# --------------------------------------------------------------------------- #
def arcface_embedding(image_path) -> Optional[np.ndarray]:
    """L2-normalised ArcFace embedding of the largest face in ``image_path``.

    Returns None when insightface is unavailable OR no face is detected. This is
    an embedding, not a face-swap — recognition model only.
    """
    fa = _face_app()
    if fa is None:
        return None
    image_path = Path(image_path)
    if not image_path.is_file():
        return None
    try:
        import cv2  # type: ignore  (ships with insightface's deps)

        img = cv2.imread(str(image_path))
        if img is None:
            return None
        faces = fa.get(img)
    except Exception as exc:
        log.debug("arcface embedding failed for %s: %s", image_path.name, exc)
        return None
    if not faces:
        return None
    # Largest detected face by bbox area — the subject, not a background bystander.
    face = max(faces, key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])))
    emb = getattr(face, "normed_embedding", None)
    if emb is None:
        emb = getattr(face, "embedding", None)
        if emb is None:
            return None
        emb = np.asarray(emb, dtype=np.float32)
        n = float(np.linalg.norm(emb)) or 1.0
        emb = emb / n
    return np.asarray(emb, dtype=np.float32)


def identity_similarity(emb_a: Optional[np.ndarray], emb_b: Optional[np.ndarray]) -> float:
    """Cosine similarity of two embeddings in [-1, 1]. Returns 0.0 if either is
    missing (unknown, not a match)."""
    if emb_a is None or emb_b is None:
        return 0.0
    a = np.asarray(emb_a, dtype=np.float32).ravel()
    b = np.asarray(emb_b, dtype=np.float32).ravel()
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na = float(np.linalg.norm(a)) or 1.0
    nb = float(np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / (na * nb))


# --------------------------------------------------------------------------- #
# Frame-level QC gate
# --------------------------------------------------------------------------- #
def check_frames(video_path, canonical_emb: Optional[np.ndarray],
                 threshold: float = DEFAULT_THRESHOLD, *, n_frames: int = 5) -> dict:
    """Sample ~``n_frames`` frames from ``video_path`` and score each face's
    similarity to ``canonical_emb``.

    Returns a dict with ``passed`` and (when the gate ran) ``min_sim`` /
    ``mean_sim`` / per-frame detail. When insightface is unavailable, or no
    canonical embedding was minted, the gate is SKIPPED — it returns
    ``{"passed": True, "skipped": True, ...}`` and never blocks a render. This is
    a QC signal, not a hard dependency.
    """
    result = {"passed": True, "skipped": True, "min_sim": None, "mean_sim": None,
              "frames_scored": 0, "frames_no_face": 0, "threshold": threshold}

    if canonical_emb is None or _face_app() is None:
        log.info("identity check_frames skipped (%s) for %s",
                 "no canonical embedding" if canonical_emb is None else "insightface absent",
                 Path(video_path).name)
        return result

    frames = _extract_frames(video_path, n_frames)
    if not frames:
        log.info("identity check_frames: could not extract frames from %s — skipping.",
                 Path(video_path).name)
        return result

    sims: list[float] = []
    no_face = 0
    for f in frames:
        emb = arcface_embedding(f)
        if emb is None:
            no_face += 1
            continue
        sims.append(identity_similarity(canonical_emb, emb))

    if not sims:
        # Frames extracted but no face found anywhere the character should be —
        # a real drift/QC signal, but still non-blocking (log loud, don't crash).
        log.warning("identity check_frames: no faces detected in %d frames of %s.",
                    len(frames), Path(video_path).name)
        return {"passed": False, "skipped": False, "min_sim": None, "mean_sim": None,
                "frames_scored": 0, "frames_no_face": no_face, "threshold": threshold}

    min_sim = float(min(sims))
    mean_sim = float(sum(sims) / len(sims))
    passed = min_sim >= threshold
    log.info("identity check_frames %s: mean=%.3f min=%.3f (thr=%.2f, %d faces / %d frames) → %s",
             Path(video_path).name, mean_sim, min_sim, threshold, len(sims), len(frames),
             "PASS" if passed else "DRIFT")
    return {"passed": passed, "skipped": False, "min_sim": round(min_sim, 4),
            "mean_sim": round(mean_sim, 4), "frames_scored": len(sims),
            "frames_no_face": no_face, "threshold": threshold}


def _extract_frames(video_path, n_frames: int) -> list[Path]:
    """Pull ~``n_frames`` evenly-spaced frames as PNGs via ffmpeg. Returns [] on
    any failure (probe/extract) — the caller treats that as skip, not crash."""
    import shutil

    video_path = Path(video_path)
    if not shutil.which("ffmpeg") or not video_path.is_file():
        return []
    from .tts import media_duration

    dur = media_duration(video_path)
    tmp = Path(tempfile.mkdtemp(prefix="mark-idqc-"))
    out: list[Path] = []
    if dur and dur > 0:
        # Evenly spaced, avoiding the very first/last frame (fades, black).
        step = dur / (n_frames + 1)
        stamps = [round(step * (i + 1), 3) for i in range(n_frames)]
    else:
        stamps = [0.0]
    for i, ts in enumerate(stamps):
        fp = tmp / f"frame_{i:02d}.png"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
             "-frames:v", "1", "-q:v", "2", str(fp)],
            capture_output=True, text=True)
        if proc.returncode == 0 and fp.is_file():
            out.append(fp)
    return out
