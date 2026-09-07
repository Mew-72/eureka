# Face Identification and Verification Pipeline

CLI-only implementation of the HH Goa 2026 Task 3 pipeline

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Face encoding, Google Vision search, ranking, content retrieval, Supabase storage, SHA-256 | Implemented |
| 2 | Opt-in PimEyes search and cross-provider merge | Implemented (best-effort) |
| 3 | Local Ethereum or Polygon Amoy anchoring and verification | Implemented |

There is no frontend or hosted application.

## Pipeline flow

1. Validate that authorized biometric use was explicitly confirmed.
2. Detect exactly one face with YuNet and create a 128-dimensional SFace embedding.
3. Send the original image bytes to Google Vision Web Detection and, when
   explicitly enabled, run PimEyes browser automation in parallel.
4. Normalize, deduplicate, and rank matching page URLs across both providers.
5. Retrieve the selected page's public metadata and matching image when available.
6. Compute `SHA-256(image_bytes + matched_url + fingerprint_timestamp)`.
7. Upload evidence to a private Supabase Storage bucket and insert its record in Postgres.
8. Write the stored hash and source URL to a local Ethereum transaction or the immutable Polygon Amoy contract.
9. Read the chain data back and compare it with the independently recomputed hash and URL.

`match_score` uses Google Vision's page relevance score when available, with the
image relevance or result category/order as a fallback. It ranks search evidence;
it is not face-identification confidence.

If the selected matching image cannot be downloaded because its host blocks the
request, the pipeline remains reproducible by hashing the stored probe image with
the discovered page URL and timestamp. `fingerprint_image_source` clearly records
whether `matched` or `probe` bytes were used.

## Requirements

- Python 3.11 recommended
- Google Cloud project with Cloud Vision API enabled
- Google service-account JSON with permission to call Vision
- Latest Google Chrome when using the optional PimEyes provider
- Supabase project
- No blockchain account or RPC for the zero-configuration local demo
- For optional Polygon Amoy use: an RPC endpoint and funded testnet wallet
- A consented image or a permissively licensed image of a public figure

Face detection and encoding use OpenCV YuNet and SFace, avoiding the native
`dlib` build required by `face_recognition`. Their verified OpenCV Zoo ONNX model
files are downloaded separately and kept out of Git because SFace is about 37 MiB.

## Setup

### 1. Create an environment

PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\download_face_models.py
```

The model download script verifies SHA-256 checksums and skips files that are
already installed in `models/`.

For development and tests:

```powershell
pip install -r requirements-dev.txt
```

### 2. Configure Google Vision

1. Enable **Cloud Vision API** in Google Cloud.
2. Create a service account with permission to call the API.
3. Download its JSON key to a location outside this repository.
4. Copy `.env.example` to `.env` and set `GOOGLE_APPLICATION_CREDENTIALS` to the
   absolute key-file path.

Do not commit the service-account JSON. The repository ignores all JSON files by
default to reduce accidental credential exposure.

### 3. Configure Supabase

1. Open the Supabase SQL editor.
2. Run `supabase_schema.sql` once. It enables `pgvector`, creates the private
   `face-evidence` bucket, and creates `public.face_records`.
3. In `.env`, set:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

The service-role key is appropriate only for this trusted local CLI. It bypasses
Row Level Security and must never be committed, logged, or used in frontend code.
No public table or Storage policies are created.

If bucket or table environment names are changed, update and rerun the matching
parts of `supabase_schema.sql` as well.

### 4. Choose a blockchain mode

The fastest demo uses the in-memory `EthereumTester` simulated chain included in
the Python dependencies. It needs no account, faucet, RPC endpoint, Solidity compiler, or
contract deployment. The pipeline mines a transaction containing the UUID,
fingerprint, and source URL, fetches that transaction back, and verifies all
three values before exiting.

The local chain exists only for that process. This is acceptable under the task's
local/simulated-chain option and ideal for a short recording, but a transaction
cannot be queried after the command exits.

#### Optional: configure and deploy Polygon Amoy

Phase 3 needs a dedicated testnet wallet and an Amoy RPC endpoint. Never use a
mainnet wallet or commit its private key. Fund the wallet with Amoy POL from a
Polygon faucet, then set these values in `.env`:

```dotenv
POLYGON_RPC_URL=https://your-amoy-rpc-endpoint
POLYGON_CHAIN_ID=80002
POLYGON_PRIVATE_KEY=0x...
```

Compile and deploy the immutable `blockchain/contracts/FaceRecord.sol` contract:

```powershell
python -m blockchain.deploy --install-solc
```

`--install-solc` downloads Solidity compiler `0.8.24` on first use. The command
prints the deployment transaction and contract address. Add the address to `.env`:

```dotenv
FACE_RECORD_CONTRACT_ADDRESS=0x...
```

The source URL and fingerprint are public once anchored. The raw image, face
embedding, timestamp, and other evidence remain in private Supabase storage.
The contract is permissionless but write-once: no account can overwrite an
existing record ID.

## Usage

Run the complete zero-configuration blockchain demo with Google Vision:

```powershell
python main.py run path\to\probe.jpg --confirm-authorized-use --local-chain
```

Opt in to PimEyes and merge both providers:

```powershell
python main.py run path\to\probe.jpg --confirm-authorized-use --use-pimeyes --local-chain
```

Omit `--local-chain` to use the configured Polygon Amoy contract instead. To
persist an off-chain record without submitting any blockchain transaction, add
`--skip-blockchain`. It can be anchored later:

```powershell
python main.py anchor RECORD_UUID
```

`--use-pimeyes` sends the probe image to PimEyes and programmatically accepts the
search dialog, so use it only after reviewing and agreeing to PimEyes' current terms.
The default is headless Chrome; add `--show-pimeyes-browser` to observe or debug the
browser flow. Set `PIMEYES_HEADLESS=false` to make visible Chrome the environment
default and `PIMEYES_TIMEOUT_SECONDS=30` to tune browser waits.

Machine-readable local-demo output:

```powershell
python main.py run path\to\probe.jpg --confirm-authorized-use --local-chain --json
```

The CLI rejects images containing zero or multiple detected faces, images above
the private bucket's 15 MiB limit, and content URLs resolving to private/local
networks. Logs show each pipeline stage for demo narration.

### Short screen-recording path

1. Before recording, install dependencies/models, configure Google Vision and
   Supabase, run the SQL schema, and complete one rehearsal.
2. Start with `elon.webp` visible briefly so the face input is clear.
3. Open a large terminal and run:

   ```powershell
   python main.py run elon.webp --confirm-authorized-use --local-chain
   ```

4. Keep the recording on the logs showing face encoding, live Google search,
   selected external URL, Supabase persistence, local block write, and read-back.
5. End with `matched_url`, `sha256_hash`, `chain_tx_hash`, and
   `blockchain_verified: True` visible.

A genuine web request can exceed 30 seconds. Do not cut or hardcode the result to
force that duration; a plain 45–90 second recording is stronger evidence if the
live provider is slower.

### Local integrity check

This is an off-chain development check, not the final PRD verification claim:

```powershell
python main.py verify-local RECORD_UUID
```

It downloads the exact image used for the fingerprint and recomputes the hash.
Exit code `0` means the stored hash matches; exit code `2` means it does not.
The full on-chain verification downloads the same private evidence object,
recomputes the fingerprint, reads the contract, and independently compares both
the hash and source URL:

```powershell
python main.py verify RECORD_UUID
```

Exit code `0` means all stored, recomputed, and on-chain values agree. Exit code
`2` means the record is missing on-chain or a hash/URL comparison failed. Reads
need `POLYGON_RPC_URL` and `FACE_RECORD_CONTRACT_ADDRESS`, but no private key.

## PimEyes behavior

`search/pimeyes_scraper.py` uses standard Selenium with the locally installed Chrome.
Google Vision and PimEyes run in parallel, then their `models.SearchResult` objects
are passed to `merge_and_rank(google_results, pimeyes_results)`.

The adapter records only real external source-page URLs exposed in the PimEyes
results DOM. It deliberately does not treat the PimEyes search-session URL as a
match. Free or logged-out searches may display thumbnails without exposing source
URLs; in that case the adapter returns no results. CAPTCHA, rate-limit, browser,
and DOM failures are logged and converted to an empty list so Google Vision can
still complete the run.

No proxy rotation, CAPTCHA bypass, or anti-detection behavior is included. PimEyes
result scores preserve displayed rank and are not face-match probabilities.

## Phase 3 blockchain implementation

### Local demo mode

`--local-chain` starts an `EthereumTester` simulated chain in memory and mines a
zero-value transaction whose input contains a canonical versioned payload:

```text
face-record:v1:{"content_hash":"...","record_id":"...","source_url":"..."}
```

The same process retrieves the mined transaction by hash, decodes its input,
re-downloads the private fingerprint image from Supabase, recomputes its hash,
and requires the UUID, fingerprint, and source URL to match before reporting
`blockchain_verified: True`. This is the simplest submission/demo path. The
local transaction hash is displayed but is not saved as durable Polygon history.

### Polygon Amoy mode

Each `face_records` row includes:

- `id`: recommended external record ID
- `sha256_hash`: 64-character lowercase SHA-256 value
- `matched_url`: source URL to store with the contract record
- `fingerprint_timestamp`: exact timestamp included in the hash
- `fingerprint_storage_path`: exact private object used for recomputation
- `chain_tx_hash`: nullable Polygon anchor transaction hash

The hash algorithm is deliberately the PRD formula with no separators:

```text
SHA-256(image bytes || matched URL UTF-8 || fingerprint timestamp UTF-8)
```

The blockchain implementation uses the already stored `sha256_hash`; it does
not generate a new timestamp, normalize the URL, or rehash the hexadecimal
fingerprint. A Supabase UUID is represented on-chain as its 16 raw bytes
left-padded to `bytes32`.

`FaceRecord.storeRecord(recordId, hash, sourceUrl)` writes each record exactly
once and emits `RecordStored`. `getRecord(recordId)` supplies the hash, source
URL, block timestamp, and submitting wallet for verification. After a confirmed
write, the CLI saves the transaction hash to `face_records.chain_tx_hash`.

If anchoring fails after Supabase persistence, the log prints the record UUID and
`python main.py anchor RECORD_UUID` safely resumes the final step. Repeating an
anchor for identical evidence is idempotent; evidence that differs from an
existing contract record is rejected.

## Tests

Tests avoid live API calls and credentials:

```powershell
python -m unittest discover -s tests -v
```

They cover canonical fingerprinting, blockchain UUID/hash and local transaction
payload encoding, URL normalization, cross-provider result merging,
deduplication, Google Vision response parsing, and PimEyes DOM candidate
normalization. Live Amoy deployment,
transaction, and Supabase tests require credentials and are intentionally not
part of the unit suite.

## Known limitations

- Google Vision Web Detection primarily identifies matching or visually similar
  image pages; it is not a general facial-embedding search engine.
- Social platforms commonly block crawlers and direct image retrieval.
- Page metadata and matched-image retrieval are best-effort because source sites
  may require authentication, JavaScript, or anti-bot checks.
- PimEyes automation is inherently unstable (CAPTCHA, IP rate limits, paywalled
  source links, and DOM changes) and is best-effort, not guaranteed, in any run.
- Public figures generally produce more reliable web results than ordinary people.
- SFace and legacy dlib embeddings are not mutually comparable even though both
  contain 128 values; each record stores its embedding model in `metadata`.
- Blockchain anchoring proves that the fingerprint and recorded source URL have
  not changed since anchoring; it does not prove that the source post was authentic.
- The `EthereumTester` chain is ephemeral and supports immediate read-back only;
  use Polygon Amoy when a durable, independently queryable transaction is needed.
- The source URL and fingerprint are permanently public on Polygon Amoy.
- The testnet wallet private key is stored locally in `.env`; production use
  would require managed signing and stronger operational controls.
- This is a hackathon testnet demonstration, not a production identity system.

Use only consented images or permissively licensed public-figure images. Do not
use this pipeline for stalking, harassment, access control, or high-impact
identity decisions.
