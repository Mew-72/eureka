// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Immutable face-evidence fingerprint registry
/// @notice Stores only a fingerprint and source URL; biometric data remains off-chain.
contract FaceRecord {
    struct Record {
        bytes32 contentHash;
        string sourceUrl;
        uint256 anchoredAt;
        address submitter;
    }

    mapping(bytes32 recordId => Record record) private records;

    error EmptyContentHash();
    error EmptyRecordId();
    error EmptySourceUrl();
    error RecordAlreadyExists(bytes32 recordId);

    event RecordStored(
        bytes32 indexed recordId,
        bytes32 indexed contentHash,
        string sourceUrl,
        uint256 anchoredAt,
        address indexed submitter
    );

    /// @dev A record is write-once so a later transaction cannot replace its proof.
    function storeRecord(
        bytes32 recordId,
        bytes32 contentHash,
        string calldata sourceUrl
    ) external {
        if (recordId == bytes32(0)) revert EmptyRecordId();
        if (contentHash == bytes32(0)) revert EmptyContentHash();
        if (bytes(sourceUrl).length == 0) revert EmptySourceUrl();
        if (records[recordId].anchoredAt != 0) {
            revert RecordAlreadyExists(recordId);
        }

        uint256 anchoredAt = block.timestamp;
        records[recordId] = Record({
            contentHash: contentHash,
            sourceUrl: sourceUrl,
            anchoredAt: anchoredAt,
            submitter: msg.sender
        });

        emit RecordStored(
            recordId,
            contentHash,
            sourceUrl,
            anchoredAt,
            msg.sender
        );
    }

    function getHash(bytes32 recordId) external view returns (bytes32) {
        return records[recordId].contentHash;
    }

    function getRecord(bytes32 recordId) external view returns (Record memory) {
        return records[recordId];
    }
}
