"""Polygon contract client for anchoring and reading evidence fingerprints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from blockchain.abi import FACE_RECORD_ABI
from config import Settings


class BlockchainError(RuntimeError):
    """Raised when a contract operation cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class AnchorResult:
    record_id: str
    content_hash: str
    source_url: str
    transaction_hash: str | None
    block_number: int | None
    already_anchored: bool


@dataclass(frozen=True, slots=True)
class OnChainRecord:
    record_id: str
    content_hash: str | None
    source_url: str | None
    anchored_at: int | None
    submitter: str | None

    @property
    def exists(self) -> bool:
        return self.anchored_at is not None


def record_id_to_bytes32(record_id: str) -> bytes:
    """Encode a UUID as a left-zero-padded bytes32 contract mapping key."""
    try:
        identifier = UUID(record_id)
    except ValueError as exc:
        raise BlockchainError("Record ID must be a valid UUID") from exc
    return identifier.bytes.rjust(32, b"\0")


def sha256_to_bytes32(content_hash: str) -> bytes:
    if len(content_hash) != 64:
        raise BlockchainError(
            "SHA-256 hash must contain exactly 64 hexadecimal characters"
        )
    try:
        value = bytes.fromhex(content_hash)
    except ValueError as exc:
        raise BlockchainError(
            "SHA-256 hash must contain only hexadecimal characters"
        ) from exc
    if value == bytes(32):
        raise BlockchainError("SHA-256 hash cannot be all zeroes")
    return value


class BlockchainClient:
    def __init__(self, settings: Settings, *, require_signer: bool = False):
        rpc_url, contract_address = settings.require_blockchain_reader()
        try:
            from web3 import Web3
        except ImportError as exc:  # pragma: no cover - installation dependent
            raise BlockchainError(
                "web3 is not installed; install requirements.txt"
            ) from exc

        self._web3 = Web3(
            Web3.HTTPProvider(
                rpc_url,
                request_kwargs={"timeout": settings.request_timeout_seconds},
            )
        )
        try:
            if not self._web3.is_connected():
                raise BlockchainError(
                    "Could not connect to the configured Polygon RPC"
                )
            actual_chain_id = self._web3.eth.chain_id
        except BlockchainError:
            raise
        except Exception as exc:
            raise BlockchainError("Failed to query the configured Polygon RPC") from exc
        if actual_chain_id != settings.polygon_chain_id:
            raise BlockchainError(
                f"RPC chain ID is {actual_chain_id}; expected {settings.polygon_chain_id}"
            )

        try:
            checksum_address = Web3.to_checksum_address(contract_address)
            code = self._web3.eth.get_code(checksum_address)
        except Exception as exc:
            raise BlockchainError("Invalid or unreachable FaceRecord contract") from exc
        if not code:
            raise BlockchainError(
                "No contract bytecode exists at FACE_RECORD_CONTRACT_ADDRESS"
            )

        self._contract = self._web3.eth.contract(
            address=checksum_address, abi=FACE_RECORD_ABI
        )
        self._chain_id = settings.polygon_chain_id
        self._confirmation_timeout = settings.blockchain_confirmation_timeout_seconds
        self._private_key: str | None = None
        self._account: Any | None = None
        if require_signer:
            self._private_key = settings.require_blockchain_writer()[2]
            try:
                self._account = self._web3.eth.account.from_key(self._private_key)
            except Exception as exc:
                raise BlockchainError("POLYGON_PRIVATE_KEY is invalid") from exc

    def get_record(self, record_id: str) -> OnChainRecord:
        contract_record_id = record_id_to_bytes32(record_id)
        try:
            content_hash, source_url, anchored_at, submitter = (
                self._contract.functions.getRecord(contract_record_id).call()
            )
        except Exception as exc:
            raise BlockchainError(
                f"Failed to read on-chain record {record_id}"
            ) from exc

        timestamp = int(anchored_at)
        if timestamp == 0:
            return OnChainRecord(record_id, None, None, None, None)
        return OnChainRecord(
            record_id=record_id,
            content_hash=bytes(content_hash).hex(),
            source_url=str(source_url),
            anchored_at=timestamp,
            submitter=str(submitter),
        )

    def anchor(self, record_id: str, content_hash: str, source_url: str) -> AnchorResult:
        if self._account is None or self._private_key is None:
            raise BlockchainError("A signer is required to anchor a record")
        if not source_url:
            raise BlockchainError("Source URL cannot be empty")

        contract_record_id = record_id_to_bytes32(record_id)
        contract_hash = sha256_to_bytes32(content_hash)
        existing = self.get_record(record_id)
        if existing.exists:
            if existing.content_hash != content_hash or existing.source_url != source_url:
                raise BlockchainError(
                    f"Record {record_id} is already anchored with different evidence"
                )
            return AnchorResult(
                record_id=record_id,
                content_hash=content_hash,
                source_url=source_url,
                transaction_hash=None,
                block_number=None,
                already_anchored=True,
            )

        function = self._contract.functions.storeRecord(
            contract_record_id, contract_hash, source_url
        )
        try:
            nonce = self._web3.eth.get_transaction_count(
                self._account.address, "pending"
            )
            transaction = function.build_transaction(
                {
                    "from": self._account.address,
                    "nonce": nonce,
                    "chainId": self._chain_id,
                }
            )
            estimated_gas = self._web3.eth.estimate_gas(transaction)
            transaction["gas"] = estimated_gas * 120 // 100
            signed = self._web3.eth.account.sign_transaction(
                transaction, self._private_key
            )
            tx_hash = self._web3.eth.send_raw_transaction(signed.raw_transaction)
        except Exception as exc:
            raise BlockchainError(f"Failed to submit record {record_id}") from exc

        tx_hash_hex = self._web3.to_hex(tx_hash)
        try:
            receipt = self._web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self._confirmation_timeout
            )
        except Exception as exc:
            raise BlockchainError(
                f"Transaction {tx_hash_hex} was submitted but confirmation failed"
            ) from exc

        if int(receipt["status"]) != 1:
            raise BlockchainError(f"Anchor transaction reverted: {tx_hash_hex}")
        return AnchorResult(
            record_id=record_id,
            content_hash=content_hash,
            source_url=source_url,
            transaction_hash=tx_hash_hex,
            block_number=int(receipt["blockNumber"]),
            already_anchored=False,
        )
