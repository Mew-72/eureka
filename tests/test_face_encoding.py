import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from face_encoding import FaceEncodingError, encode_single_face


class FakeFeature:
    def __init__(self, values: list[float]):
        self.values = values

    def reshape(self, *_shape: int) -> "FakeFeature":
        return self

    def tolist(self) -> list[float]:
        return self.values


class FaceEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(self.temporary_directory.name)
        self.image_path = directory / "probe.jpg"
        self.detector_path = directory / "yunet.onnx"
        self.recognizer_path = directory / "sface.onnx"
        for path in (self.image_path, self.detector_path, self.recognizer_path):
            path.touch()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def fake_cv2(self, faces: object, feature_size: int = 128) -> SimpleNamespace:
        image = SimpleNamespace(shape=(480, 640, 3))
        detector = SimpleNamespace(detect=lambda _image: (None, faces))
        recognizer = SimpleNamespace(
            alignCrop=lambda _image, _face: object(),
            feature=lambda _aligned: FakeFeature([0.25] * feature_size),
        )
        return SimpleNamespace(
            IMREAD_COLOR=1,
            imread=lambda _path, _mode: image,
            FaceDetectorYN=SimpleNamespace(create=lambda *_args: detector),
            FaceRecognizerSF=SimpleNamespace(create=lambda *_args: recognizer),
        )

    def encode_with(self, fake_cv2: SimpleNamespace) -> list[float]:
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            return encode_single_face(
                self.image_path,
                detector_model_path=self.detector_path,
                recognizer_model_path=self.recognizer_path,
            )

    def test_returns_128_dimensional_embedding(self) -> None:
        embedding = self.encode_with(self.fake_cv2([[0.0] * 15]))

        self.assertEqual(len(embedding), 128)
        self.assertTrue(all(value == 0.25 for value in embedding))

    def test_rejects_image_without_a_face(self) -> None:
        with self.assertRaisesRegex(FaceEncodingError, "No face"):
            self.encode_with(self.fake_cv2(None))

    def test_rejects_image_with_multiple_faces(self) -> None:
        with self.assertRaisesRegex(FaceEncodingError, "detected 2"):
            self.encode_with(self.fake_cv2([[0.0] * 15, [1.0] * 15]))

    def test_rejects_wrong_embedding_size(self) -> None:
        with self.assertRaisesRegex(FaceEncodingError, "128-dimensional"):
            self.encode_with(self.fake_cv2([[0.0] * 15], feature_size=127))

    def test_reports_missing_models_before_loading_opencv(self) -> None:
        with self.assertRaisesRegex(FaceEncodingError, "download_face_models.py"):
            encode_single_face(
                self.image_path,
                detector_model_path=self.detector_path.with_name("missing-yunet.onnx"),
                recognizer_model_path=self.recognizer_path,
            )


if __name__ == "__main__":
    unittest.main()
