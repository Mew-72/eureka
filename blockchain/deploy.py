"""Compile and deploy FaceRecord to the configured Polygon network."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from config import ConfigurationError, Settings

SOLC_VERSION = "0.8.24"
CONTRACT_PATH = Path(__file__).parent / "contracts" / "FaceRecord.sol"


def _compile_contract(install_solc: bool) -> tuple[list[dict[str, Any]], str]:
    try:
        import solcx
    except ImportError as exc:
        raise RuntimeError(
            "py-solc-x is not installed; install requirements.txt"
        ) from exc

    installed = {str(version) for version in solcx.get_installed_solc_versions()}
    if SOLC_VERSION not in installed:
        if not install_solc:
            raise RuntimeError(
                f"Solidity compiler {SOLC_VERSION} is missing; rerun with --install-solc"
            )
        solcx.install_solc(SOLC_VERSION)

    source = CONTRACT_PATH.read_text(encoding="utf-8")
    compiled = solcx.compile_standard(
        {
            "language": "Solidity",
            "sources": {CONTRACT_PATH.name: {"content": source}},
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
            },
        },
        solc_version=SOLC_VERSION,
    )
    contract = compiled["contracts"][CONTRACT_PATH.name]["FaceRecord"]
    return contract["abi"], contract["evm"]["bytecode"]["object"]


def deploy(settings: Settings, *, install_solc: bool = False) -> dict[str, Any]:
    rpc_url, private_key = settings.require_blockchain_deployer()
    try:
        from web3 import Web3
    except ImportError as exc:
        raise RuntimeError("web3 is not installed; install requirements.txt") from exc

    abi, bytecode = _compile_contract(install_solc)
    web3 = Web3(
        Web3.HTTPProvider(
            rpc_url,
            request_kwargs={"timeout": settings.request_timeout_seconds},
        )
    )
    if not web3.is_connected():
        raise RuntimeError("Could not connect to the configured Polygon RPC")
    actual_chain_id = web3.eth.chain_id
    if actual_chain_id != settings.polygon_chain_id:
        raise RuntimeError(
            f"RPC chain ID is {actual_chain_id}; expected {settings.polygon_chain_id}"
        )

    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)
    transaction = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address, "pending"),
            "chainId": settings.polygon_chain_id,
        }
    )
    transaction["gas"] = web3.eth.estimate_gas(transaction) * 120 // 100
    signed = web3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(
        tx_hash, timeout=settings.blockchain_confirmation_timeout_seconds
    )
    if int(receipt["status"]) != 1:
        raise RuntimeError(
            f"Deployment transaction reverted: {web3.to_hex(tx_hash)}"
        )

    return {
        "contract_address": receipt["contractAddress"],
        "transaction_hash": web3.to_hex(tx_hash),
        "block_number": int(receipt["blockNumber"]),
        "chain_id": settings.polygon_chain_id,
        "deployer": account.address,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy FaceRecord to Polygon Amoy")
    parser.add_argument(
        "--install-solc",
        action="store_true",
        help=f"Download Solidity compiler {SOLC_VERSION} if it is not installed",
    )
    args = parser.parse_args()
    try:
        result = deploy(Settings.from_env(), install_solc=args.install_solc)
        print(json.dumps(result, indent=2, sort_keys=True))
        print(
            "Set FACE_RECORD_CONTRACT_ADDRESS=" + result["contract_address"],
            file=sys.stderr,
        )
        return 0
    except (ConfigurationError, OSError, RuntimeError, ValueError) as exc:
        print(f"Deployment failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
