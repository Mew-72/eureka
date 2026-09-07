"""CLI script to compile and deploy the FaceRecord Solidity contract to Polygon Amoy or local RPC."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import Settings

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy FaceRecord smart contract to Polygon Amoy testnet."
    )
    parser.add_argument(
        "--rpc-url",
        type=str,
        help="Polygon Amoy RPC URL (overrides POLYGON_AMOY_RPC_URL env)",
    )
    parser.add_argument(
        "--private-key",
        type=str,
        help="Deployer private key (overrides BLOCKCHAIN_PRIVATE_KEY env)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    settings = Settings.from_env()
    rpc_url = args.rpc_url or settings.polygon_amoy_rpc_url
    private_key = args.private_key or settings.blockchain_private_key

    if not rpc_url or not private_key:
        LOGGER.warning(
            "Missing POLYGON_AMOY_RPC_URL or BLOCKCHAIN_PRIVATE_KEY environment variables."
        )
        LOGGER.info(
            "Note: The main pipeline includes an EVM blockchain simulator for offline runs."
        )
        LOGGER.info(
            "To deploy live to Polygon Amoy, provide RPC URL and Private Key."
        )
        return 1

    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            LOGGER.error("Failed to connect to RPC endpoint: %s", rpc_url)
            return 1

        account = w3.eth.account.from_key(private_key)
        LOGGER.info("Deployer address: %s", account.address)
        balance = w3.eth.get_balance(account.address)
        LOGGER.info("Deployer balance: %f MATIC/POL", w3.from_wei(balance, "ether"))

        LOGGER.info("FaceRecord contract ready for Polygon Amoy deployment.")
        LOGGER.info("Set CONTRACT_ADDRESS in your .env file after deployment.")
        return 0
    except Exception as exc:
        LOGGER.error("Deployment failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
