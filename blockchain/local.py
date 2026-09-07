"""Ephemeral Ethereum test-chain anchoring for a zero-configuration demo."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from blockchain.client import BlockchainError, record_id_to_bytes32, sha256_to_bytes32

PAYLOAD_PREFIX = b"face-record:v1:"


@dataclass(frozen=True, slots=True)
class LocalChainResult:
    record_id: str
    content_hash: str
    source_url: str
    transaction_hash: str
    block_number: int
    verified: bool
    chain: str = "EthereumTester"


def encode_payload(record_id: str, content_hash: str, source_url: str) -> bytes:
    record_id_to_bytes32(record_id)
    sha256_to_bytes32(content_hash)
    if not source_url:
        raise BlockchainError("Source URL cannot be empty")
    body = json.dumps(
        {
            "content_hash": content_hash,
            "record_id": record_id,
            "source_url": source_url,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return PAYLOAD_PREFIX + body


def decode_payload(payload: bytes) -> dict[str, str]:
    if not payload.startswith(PAYLOAD_PREFIX):
        raise BlockchainError("Transaction does not contain a FaceRecord payload")
    try:
        decoded = json.loads(payload[len(PAYLOAD_PREFIX) :].decode("utf-8"))
        record_id = str(decoded["record_id"])
        content_hash = str(decoded["content_hash"])
        source_url = str(decoded["source_url"])
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlockchainError("Transaction contains an invalid FaceRecord payload") from exc
    record_id_to_bytes32(record_id)
    sha256_to_bytes32(content_hash)
    return {
        "record_id": record_id,
        "content_hash": content_hash,
        "source_url": source_url,
    }


class LocalBlockchainSession:
    """Mine and re-read one evidence transaction on an in-memory test chain."""

    def __init__(self) -> None:
        try:
            # eth-tester announces unavailable optional backends while importing.
            # The explicit lightweight backend is intentional for this demo mode.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                from eth_tester import EthereumTester, MockBackend
                from web3 import EthereumTesterProvider, Web3
                tester = EthereumTester(backend=MockBackend())
            self._web3 = Web3(EthereumTesterProvider(tester))
        except ImportError as exc:  # pragma: no cover - installation dependent
            raise BlockchainError(
                "web3 and eth-tester are required; install requirements.txt"
            ) from exc
        try:
            self._account = self._web3.eth.accounts[0]
        except Exception as exc:
            raise BlockchainError("Failed to start the local Ethereum test chain") from exc

    def anchor_and_verify(
        self, record_id: str, content_hash: str, source_url: str
    ) -> LocalChainResult:
        expected_payload = encode_payload(record_id, content_hash, source_url)
        try:
            tx_hash = self._web3.eth.send_transaction(
                {
                    "from": self._account,
                    "to": self._account,
                    "value": 0,
                    "gas": 500_000,
                    "data": expected_payload,
                }
            )
            receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash)
            transaction = self._web3.eth.get_transaction(tx_hash)
            block = self._web3.eth.get_block(receipt["blockNumber"])
            actual_payload = bytes(transaction["input"])
            decoded = decode_payload(actual_payload)
        except BlockchainError:
            raise
        except Exception as exc:
            raise BlockchainError("Local blockchain transaction failed") from exc

        verified = (
            tx_hash in block["transactions"]
            and actual_payload == expected_payload
            and decoded["record_id"] == record_id
            and decoded["content_hash"] == content_hash
            and decoded["source_url"] == source_url
        )
        if not verified:
            raise BlockchainError("Local on-chain read-back did not match the evidence")
        return LocalChainResult(
            record_id=record_id,
            content_hash=content_hash,
            source_url=source_url,
            transaction_hash=self._web3.to_hex(tx_hash),
            block_number=int(receipt["blockNumber"]),
            verified=True,
        )
