"""Face detection and 128-dimensional encoding with OpenCV YuNet/SFace."""

from __future__ import annotations

import importlib
import math
from pathlib import Path


class FaceEncodingError(RuntimeError):
    """Raised when a usable single-face encoding cannot be produced."""


MODEL_DIRECTORY = Path(__file__).resolve().parent / "models"
DEFAULT_DETECTOR_MODEL = MODEL_DIRECTORY / "face_detection_yunet_2023mar.onnx"
DEFAULT_RECOGNIZER_MODEL = MODEL_DIRECTORY / "face_recognition_sface_2021dec.onnx"
EMBEDDING_MODEL = "opencv_sface_2021dec"


def encode_single_face(
    image_path: Path,
    *,
    detector_model_path: Path = DEFAULT_DETECTOR_MODEL,
    recognizer_model_path: Path = DEFAULT_RECOGNIZER_MODEL,
) -> list[float]:
    """Detect exactly one face and return its 128-dimensional SFace encoding."""
    missing_models = [
        path.name
        for path in (detector_model_path, recognizer_model_path)
        if not path.is_file()
    ]
    if missing_models:
        raise FaceEncodingError(
            "Missing OpenCV face model(s): "
            f"{', '.join(missing_models)}. Run: python scripts/download_face_models.py"
        )

    try:
        cv2 = importlib.import_module("cv2")
    except ImportError as exc:  # pragma: no cover - depends on installation
        raise FaceEncodingError(
            "opencv-python-headless is not installed; install requirements.txt"
        ) from exc

    try:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    except Exception as exc:
        raise FaceEncodingError(f"Could not load image: {image_path}") from exc
    if image is None:
        raise FaceEncodingError(f"Could not load image: {image_path}")

    height, width = image.shape[:2]
    if width < 1 or height < 1:
        raise FaceEncodingError("Input image has invalid dimensions")

    try:
        detector = cv2.FaceDetectorYN.create(
            str(detector_model_path), "", (width, height), 0.9, 0.3, 5000
        )
        _, faces = detector.detect(image)
    except Exception as exc:
        raise FaceEncodingError("OpenCV YuNet face detection failed") from exc

    if faces is None or len(faces) == 0:
        raise FaceEncodingError("No face was detected in the input image")

    face_count = len(faces)
    if face_count > 1:
        raise FaceEncodingError(
            f"Expected one face, but detected {face_count}; use a single-face image"
        )

    try:
        recognizer = cv2.FaceRecognizerSF.create(str(recognizer_model_path), "")
        aligned_face = recognizer.alignCrop(image, faces[0])
        embedding = recognizer.feature(aligned_face).reshape(-1).tolist()
    except Exception as exc:
        raise FaceEncodingError("OpenCV SFace encoding failed") from exc

    if len(embedding) != 128 or not all(math.isfinite(value) for value in embedding):
        raise FaceEncodingError("Failed to generate a valid 128-dimensional face encoding")

    return [float(value) for value in embedding]
