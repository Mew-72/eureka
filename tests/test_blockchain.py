import unittest
from uuid import UUID

from blockchain.client import BlockchainError, record_id_to_bytes32, sha256_to_bytes32


class BlockchainEncodingTests(unittest.TestCase):
    def test_uuid_is_left_padded_to_bytes32(self) -> None:
        record_id = "12345678-1234-5678-9abc-def012345678"

        encoded = record_id_to_bytes32(record_id)

        self.assertEqual(len(encoded), 32)
        self.assertEqual(encoded[:16], bytes(16))
        self.assertEqual(encoded[16:], UUID(record_id).bytes)

    def test_rejects_invalid_record_id(self) -> None:
        with self.assertRaisesRegex(BlockchainError, "valid UUID"):
            record_id_to_bytes32("not-a-uuid")

    def test_hash_is_encoded_without_rehashing(self) -> None:
        content_hash = "ab" * 32

        self.assertEqual(sha256_to_bytes32(content_hash), bytes.fromhex(content_hash))

    def test_rejects_invalid_hash(self) -> None:
        for content_hash in ("ab", "z" * 64, "0" * 64):
            with self.subTest(content_hash=content_hash), self.assertRaises(
                BlockchainError
            ):
                sha256_to_bytes32(content_hash)


if __name__ == "__main__":
    unittest.main()
