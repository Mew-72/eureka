"""Download and verify the OpenCV Zoo models used by the face encoder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib import request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIRECTORY = PROJECT_ROOT / "models"
MODELS = (
    (
        "face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    (
        "face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_model(filename: str, url: str, expected_sha256: str) -> None:
    destination = MODEL_DIRECTORY / filename
    if destination.is_file() and sha256_file(destination) == expected_sha256:
        print(f"Verified {destination.relative_to(PROJECT_ROOT)}")
        return

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    download_request = request.Request(
        url, headers={"User-Agent": "FaceRecog-model-downloader/1.0"}
    )
    print(f"Downloading {filename}...")

    try:
        with (
            request.urlopen(download_request, timeout=120) as response,
            temporary.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                output.write(chunk)

        actual_sha256 = sha256_file(temporary)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Checksum mismatch for {filename}: expected {expected_sha256}, "
                f"received {actual_sha256}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"Installed {destination.relative_to(PROJECT_ROOT)}")


def main() -> None:
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        download_model(*model)


if __name__ == "__main__":
    main()
