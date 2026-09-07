// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FaceRecord
 * @dev Tamper-evident record registry for face identification search matches.
 */
contract FaceRecord {
    struct Record {
        bytes32 recordId;
        bytes32 sha256Hash;
        string sourceUrl;
        uint256 timestamp;
        address submitter;
    }

    // Mapping from recordId to stored Record struct
    mapping(bytes32 => Record) private _records;

    // List of all registered recordIds
    bytes32[] private _recordIds;

    // Events
    event RecordAnchored(
        bytes32 indexed recordId,
        bytes32 sha256Hash,
        string sourceUrl,
        uint256 timestamp,
        address indexed submitter
    );

    /**
     * @notice Store a tamper-evident record of a face match on-chain.
     * @param recordId Unique UUID or identifier formatted as bytes32.
     * @param sha256Hash SHA-256 fingerprint hash as bytes32.
     * @param sourceUrl Matched social media / web URL.
     */
    function storeRecord(
        bytes32 recordId,
        bytes32 sha256Hash,
        string calldata sourceUrl
    ) external {
        require(_records[recordId].timestamp == 0, "Record ID already exists");
        require(sha256Hash != bytes32(0), "Hash cannot be empty");

        Record memory newRecord = Record({
            recordId: recordId,
            sha256Hash: sha256Hash,
            sourceUrl: sourceUrl,
            timestamp: block.timestamp,
            submitter: msg.sender
        });

        _records[recordId] = newRecord;
        _recordIds.push(recordId);

        emit RecordAnchored(
            recordId,
            sha256Hash,
            sourceUrl,
            block.timestamp,
            msg.sender
        );
    }

    /**
     * @notice Retrieve stored record data by recordId.
     * @param recordId Unique record identifier.
     */
    function getRecord(bytes32 recordId)
        external
        view
        returns (
            bytes32 sha256Hash,
            string memory sourceUrl,
            uint256 timestamp,
            address submitter
        )
    {
        Record memory rec = _records[recordId];
        require(rec.timestamp != 0, "Record ID not found");
        return (rec.sha256Hash, rec.sourceUrl, rec.timestamp, rec.submitter);
    }

    /**
     * @notice Check whether a given SHA-256 hash matches the on-chain record.
     * @param recordId Unique record identifier.
     * @param sha256Hash Expected SHA-256 hash.
     * @return bool True if hash matches exactly.
     */
    function verifyRecord(bytes32 recordId, bytes32 sha256Hash)
        external
        view
        returns (bool)
    {
        Record memory rec = _records[recordId];
        if (rec.timestamp == 0) {
            return false;
        }
        return rec.sha256Hash == sha256Hash;
    }

    /**
     * @notice Get total count of anchored records.
     */
    function getRecordCount() external view returns (uint256) {
        return _recordIds.length;
    }
}
