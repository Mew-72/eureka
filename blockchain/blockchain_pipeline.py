"""Blockchain client module for writing and verifying records on Polygon Amoy / EVM testnet."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import Settings

LOGGER = logging.getLogger(__name__)
STATE_FILE = Path(__file__).resolve().parent.parent / ".blockchain_state.json"

# Standard FaceRecord Contract ABI definition
FACE_RECORD_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "recordId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "sha256Hash", "type": "bytes32"},
            {"internalType": "string", "name": "sourceUrl", "type": "string"},
        ],
        "name": "storeRecord",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "recordId", "type": "bytes32"}],
        "name": "getRecord",
        "outputs": [
            {"internalType": "bytes32", "name": "sha256Hash", "type": "bytes32"},
            {"internalType": "string", "name": "sourceUrl", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "address", "name": "submitter", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "recordId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "sha256Hash", "type": "bytes32"},
        ],
        "name": "verifyRecord",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True, slots=True)
class OnChainVerificationResult:
    record_id: str
    on_chain_hash: str
    expected_hash: str
    matches: bool
    source_url: str
    tx_hash: str | None
    block_number: int | None
    network: str


class LocalBlockchainSimulator:
    """EVM testnet state simulator with local file persistence for CLI runs."""

    def __init__(self, state_path: Path = STATE_FILE) -> None:
        self.state_path = state_path
        self._records: dict[str, dict[str, Any]] = {}
        self._tx_count = 0
        self._load()

    def _load(self) -> None:
        if self.state_path.is_file():
            try:
                data = json.loads(self.state_path.read_text("utf-8"))
                self._records = data.get("records", {})
                self._tx_count = data.get("tx_count", 0)
            except Exception as exc:
                LOGGER.warning("Could not read local blockchain state: %s", exc)

    def _save(self) -> None:
        try:
            payload = {"records": self._records, "tx_count": self._tx_count}
            self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            LOGGER.warning("Could not save local blockchain state: %s", exc)

    def store_record(
        self, record_id_uuid: str, sha256_hash: str, matched_url: str
    ) -> dict[str, Any]:
        record_key = record_id_uuid.replace("-", "").lower()
        self._tx_count += 1
        tx_hash = f"0x{record_key[:32]}{self._tx_count:032x}"
        block_number = 1000000 + self._tx_count

        self._records[record_key] = {
            "sha256_hash": sha256_hash.lower(),
            "source_url": matched_url,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "timestamp": 1773000000 + self._tx_count,
        }
        self._save()
        return {
            "tx_hash": tx_hash,
            "block_number": block_number,
            "network": "local_evm_simulator",
            "status": "confirmed",
        }

    def verify_record(self, record_id_uuid: str, expected_hash: str) -> OnChainVerificationResult:
        self._load()
        record_key = record_id_uuid.replace("-", "").lower()
        rec = self._records.get(record_key)
        if not rec:
            return OnChainVerificationResult(
                record_id=record_id_uuid,
                on_chain_hash="",
                expected_hash=expected_hash,
                matches=False,
                source_url="",
                tx_hash=None,
                block_number=None,
                network="local_evm_simulator",
            )
        stored_hash = rec["sha256_hash"]
        matches = stored_hash == expected_hash.lower()
        return OnChainVerificationResult(
            record_id=record_id_uuid,
            on_chain_hash=stored_hash,
            expected_hash=expected_hash,
            matches=matches,
            source_url=rec["source_url"],
            tx_hash=rec["tx_hash"],
            block_number=rec["block_number"],
            network="local_evm_simulator",
        )


_SIMULATOR = LocalBlockchainSimulator()


def _format_bytes32(hex_or_uuid: str) -> bytes:
    cleaned = hex_or_uuid.replace("-", "").replace("0x", "").lower()
    cleaned = cleaned.ljust(64, "0")[:64]
    return bytes.fromhex(cleaned)


def write_to_blockchain(
    record_id: str, sha256_hash: str, matched_url: str, settings: Settings
) -> dict[str, Any]:
    """Write record fingerprint hash to Polygon Amoy testnet or local EVM fallback."""
    rpc_url = settings.polygon_amoy_rpc_url
    private_key = settings.blockchain_private_key
    contract_address = settings.contract_address

    if not rpc_url or not private_key or not contract_address:
        LOGGER.info(
            "Live RPC / key not fully configured. Using EVM blockchain simulator for Phase 3."
        )
        return _SIMULATOR.store_record(record_id, sha256_hash, matched_url)

    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            LOGGER.warning("Could not connect to RPC endpoint: %s. Using local simulator.", rpc_url)
            return _SIMULATOR.store_record(record_id, sha256_hash, matched_url)

        account = w3.eth.account.from_key(private_key)
        contract = w3.eth.contract(
            address=w3.to_checksum_address(contract_address), abi=FACE_RECORD_ABI
        )

        record_bytes32 = _format_bytes32(record_id)
        hash_bytes32 = _format_bytes32(sha256_hash)

        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.storeRecord(
            record_bytes32, hash_bytes32, matched_url
        ).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "gas": 200000,
            "gasPrice": w3.eth.gas_price,
            "chainId": settings.polygon_chain_id,
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        tx_hash_hex = w3.to_hex(tx_hash)
        LOGGER.info(
            "Successfully anchored record %s on Polygon Amoy (tx: %s)",
            record_id,
            tx_hash_hex,
        )
        return {
            "tx_hash": tx_hash_hex,
            "block_number": receipt.blockNumber,
            "network": "polygon_amoy_testnet",
            "status": "confirmed",
        }
    except Exception as exc:
        LOGGER.warning(
            "Live blockchain transaction failed (%s). Falling back to EVM simulator.", exc
        )
        return _SIMULATOR.store_record(record_id, sha256_hash, matched_url)


def verify_on_chain(
    record_id: str, expected_hash: str, settings: Settings
) -> OnChainVerificationResult:
    """Read stored record from Polygon Amoy smart contract and compare SHA-256 fingerprint."""
    rpc_url = settings.polygon_amoy_rpc_url
    contract_address = settings.contract_address

    if not rpc_url or not contract_address:
        return _SIMULATOR.verify_record(record_id, expected_hash)

    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            return _SIMULATOR.verify_record(record_id, expected_hash)

        contract = w3.eth.contract(
            address=w3.to_checksum_address(contract_address), abi=FACE_RECORD_ABI
        )

        record_bytes32 = _format_bytes32(record_id)
        expected_bytes32 = _format_bytes32(expected_hash)

        on_chain_data = contract.functions.getRecord(record_bytes32).call()
        on_chain_hash_bytes = on_chain_data[0]
        source_url = on_chain_data[1]
        on_chain_hash_hex = on_chain_hash_bytes.hex().lower()

        matches = on_chain_hash_bytes == expected_bytes32

        return OnChainVerificationResult(
            record_id=record_id,
            on_chain_hash=on_chain_hash_hex,
            expected_hash=expected_hash.lower(),
            matches=matches,
            source_url=source_url,
            tx_hash=None,
            block_number=None,
            network="polygon_amoy_testnet",
        )
    except Exception as exc:
        LOGGER.warning(
            "Live blockchain verification failed (%s). Querying EVM simulator.", exc
        )
        return _SIMULATOR.verify_record(record_id, expected_hash)
