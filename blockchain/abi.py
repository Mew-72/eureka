"""ABI for the deployed FaceRecord contract."""

from __future__ import annotations

from typing import Any

FACE_RECORD_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "storeRecord",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "recordId", "type": "bytes32", "internalType": "bytes32"},
            {"name": "contentHash", "type": "bytes32", "internalType": "bytes32"},
            {"name": "sourceUrl", "type": "string", "internalType": "string"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "getHash",
        "stateMutability": "view",
        "inputs": [
            {"name": "recordId", "type": "bytes32", "internalType": "bytes32"}
        ],
        "outputs": [
            {"name": "", "type": "bytes32", "internalType": "bytes32"}
        ],
    },
    {
        "type": "function",
        "name": "getRecord",
        "stateMutability": "view",
        "inputs": [
            {"name": "recordId", "type": "bytes32", "internalType": "bytes32"}
        ],
        "outputs": [
            {
                "name": "",
                "type": "tuple",
                "internalType": "struct FaceRecord.Record",
                "components": [
                    {
                        "name": "contentHash",
                        "type": "bytes32",
                        "internalType": "bytes32",
                    },
                    {
                        "name": "sourceUrl",
                        "type": "string",
                        "internalType": "string",
                    },
                    {
                        "name": "anchoredAt",
                        "type": "uint256",
                        "internalType": "uint256",
                    },
                    {
                        "name": "submitter",
                        "type": "address",
                        "internalType": "address",
                    },
                ],
            }
        ],
    },
    {
        "type": "event",
        "name": "RecordStored",
        "anonymous": False,
        "inputs": [
            {
                "name": "recordId",
                "type": "bytes32",
                "indexed": True,
                "internalType": "bytes32",
            },
            {
                "name": "contentHash",
                "type": "bytes32",
                "indexed": True,
                "internalType": "bytes32",
            },
            {
                "name": "sourceUrl",
                "type": "string",
                "indexed": False,
                "internalType": "string",
            },
            {
                "name": "anchoredAt",
                "type": "uint256",
                "indexed": False,
                "internalType": "uint256",
            },
            {
                "name": "submitter",
                "type": "address",
                "indexed": True,
                "internalType": "address",
            },
        ],
    },
]
