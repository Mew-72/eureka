# Face Identification & Blockchain Verification Pipeline

An end-to-end CLI pipeline that detects and encodes a face from a photo, finds matching open-web/social media posts via genuine reverse-image search, and anchors a tamper-evident, verifiable fingerprint to a blockchain.

Implemented for **HH Goa 2026 — Task 3**.

---

## ✦ Phase Status & Core Architecture

| Phase | Scope | Status |
|---|---|---|
| **Phase 1** | Face detection & 128-d encoding (OpenCV YuNet + SFace), Google Vision Web Detection, canonical SHA-256 fingerprinting, Supabase storage | **Implemented** |
| **Phase 2** | Dual-source search (PimEyes scraper + Google Vision Web Detection) with deduplication & ranking | **Implemented** |
| **Phase 3** | Polygon Amoy testnet smart contract deployment, on-chain record write, and on-chain tamper verification | **Implemented** |

```
[1] Face Photo Input (e.g. elon.webp)
        │
        ▼
[2] Face Detection & 128-d Encoding (OpenCV YuNet + SFace)
        │
        ▼
[3] Dual Reverse-Image Search (Google Vision Web Detection + PimEyes scraper)
        │  ↳ Deduplicates, normalizes tracking params, and ranks best match URL
        ▼
[4] Content & Evidence Retrieval
        │  ↳ Fetches image bytes + page metadata
        ▼
[5] Canonical SHA-256 Fingerprint
        │  ↳ SHA-256(image_bytes + matched_url + timestamp)
        ▼
[6] Off-Chain Storage (Supabase Storage + Postgres pgvector)
        │
        ▼
[7] Blockchain Write & On-Chain Verification (Polygon Amoy / EVM smart contract)
        │  ↳ Calls FaceRecord.sol: storeRecord(recordId, sha256Hash, sourceUrl)
        ▼
[8] On-Chain Verification
        ↳ Calls FaceRecord.sol: verifyRecord(recordId, sha256Hash) → True/False
```

---

## ✦ Blockchain Details

- **Target Blockchain**: **Polygon Amoy Testnet** (Chain ID: `80002`) / EVM Compatible Testnets (e.g. Sepolia).
- **Smart Contract**: [`blockchain/contracts/FaceRecord.sol`](file:///c:/hhgoa/eureka/blockchain/contracts/FaceRecord.sol).
- **Fallback Capability**: Features a built-in local EVM simulator (`LocalBlockchainSimulator`) so the full pipeline executes cleanly end-to-end even without active network RPC credentials or testnet gas.

---

## ✦ Requirements & Setup

### 1. Environment & Dependencies

- Python 3.11 recommended.
- Install dependencies:

```powershell
pip install -r requirements.txt
```

- Download OpenCV face detection and recognition ONNX models (~37 MB):

```powershell
python scripts/download_face_models.py
```

### 2. Configuration (Optional `.env`)

Copy `.env.example` to `.env` if configuring live Cloud or Blockchain credentials:

```env
# Optional Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Optional Google Cloud Vision
GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/google-vision-key.json

# Optional Polygon Amoy Blockchain
POLYGON_AMOY_RPC_URL=https://rpc-amoy.polygon.technology
BLOCKCHAIN_PRIVATE_KEY=0x...
CONTRACT_ADDRESS=0x...
```

---

## ✦ Usage & Commands

### 1. Run the End-to-End Pipeline

Execute the pipeline on an input photo (requires explicit `--confirm-authorized-use` flag):

```powershell
python main.py run elon.webp --confirm-authorized-use
```

For machine-readable JSON output:

```powershell
python main.py run elon.webp --confirm-authorized-use --json
```

### 2. On-Chain Verification (Phase 3)

Verify a record hash directly against the blockchain smart contract:

```powershell
python main.py verify-onchain <RECORD_ID> <SHA256_HASH> --json
```

Output:

```json
{
  "block_number": 1000001,
  "expected_hash": "64ae1cc25f2569a9381d38553950cd15c463e1f5fdafb7bf5998e718e28725a6",
  "matches": true,
  "network": "local_evm_simulator",
  "on_chain_hash": "64ae1cc25f2569a9381d38553950cd15c463e1f5fdafb7bf5998e718e28725a6",
  "record_id": "ea0a9c5b-83de-4db3-af24-b410bc2a9141",
  "source_url": "https://x.com/elonmusk/status/1800000000000000000",
  "tx_hash": "0xea0a9c5b83de4db3af24b410bc2a914100000000000000000000000000000001"
}
```

### 3. Local Integrity Verification

```powershell
python main.py verify-local <RECORD_ID>
```

---

## ✦ Testing

Run the full automated test suite (covers face encoding, url deduplication, PimEyes graceful degradation, and blockchain hash verification):

```powershell
python -m unittest discover -s tests -v
```

---

## ✦ Known Limitations

1. **Anti-Bot & CAPTCHA Restrictions**: Social platforms (Instagram, X, PimEyes) frequently use Cloudflare anti-bot protection. PimEyes scraping is best-effort; if blocked, the pipeline degrades gracefully to Google Vision / open-web reverse image search.
2. **Public Figure Bias**: Reverse-image search accuracy is significantly higher for public figures and widely published images than for non-public individuals.
3. **Immutability vs Content Authenticity**: Blockchain anchoring proves the record hash has not been altered since creation; it does not guarantee that the upstream source page itself remains unmodified.
4. **Testnet Demonstration**: Designed as a hackathon pipeline demonstration, not a production biometric identity management system.
