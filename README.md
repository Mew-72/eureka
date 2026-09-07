# Face Identification and Verification Pipeline

CLI-only implementation of the HH Goa 2026 Task 3 pipeline described in
`Face_Identification_Blockchain_Verification_PRD.md`.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Face encoding, Google Vision search, ranking, content retrieval, Supabase storage, SHA-256 | Implemented |
| 2 | PimEyes search and cross-provider merge | Not implemented yet |
| 3 | Polygon Amoy contract write and on-chain verification | Owned separately |

There is no frontend or hosted application.

## Phase 1 flow

1. Validate that authorized biometric use was explicitly confirmed.
2. Detect exactly one face with YuNet and create a 128-dimensional SFace embedding.
3. send the original image bytes to Google Vision Web Detection.
4. Normalize, deduplicate, and rank matching page URLs.
5. Retrieve the selected page's public metadata and matching image when available.
6. Compute `SHA-256(image_bytes + matched_url + fingerprint_timestamp)`.
7. Upload evidence to a private Supabase Storage bucket and insert its record in Postgres.
8. Optionally retrieve the stored fingerprint image and recompute the hash locally.

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
- Supabase project
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

## Usage

Run Phase 1:

```powershell
python main.py run path\to\probe.jpg --confirm-authorized-use
```

Machine-readable output:

```powershell
python main.py run path\to\probe.jpg --confirm-authorized-use --json
```

The CLI rejects images containing zero or multiple detected faces, images above
the private bucket's 15 MiB limit, and content URLs resolving to private/local
networks. Logs show each pipeline stage for demo narration.

### Local integrity check

This is an off-chain development check, not the final PRD verification claim:

```powershell
python main.py verify-local RECORD_UUID
```

It downloads the exact image used for the fingerprint and recomputes the hash.
Exit code `0` means the stored hash matches; exit code `2` means it does not.
Phase 3 should compare the same recomputed hash with the Polygon contract value.

## Phase 2 integration contract

A PimEyes adapter should return `models.SearchResult` objects and pass them to:

```python
merged = merge_and_rank(google_results, pimeyes_results)
```

Required normalized fields are `source`, `page_url`, `image_url`, `match_type`,
and a provider ranking `score` from `0` to `1`. `merge_and_rank` already removes
tracking parameters, deduplicates pages, combines source names, and retains the
best available matching-image URL.

PimEyes must remain best-effort. CAPTCHA or rate-limit failures should be logged
and converted to an empty result list so Google Vision can complete the run.

## Phase 3 blockchain handoff

Each `face_records` row includes:

- `id`: recommended external record ID
- `sha256_hash`: 64-character lowercase SHA-256 value
- `matched_url`: source URL to store with the contract record
- `fingerprint_timestamp`: exact timestamp included in the hash
- `fingerprint_storage_path`: exact private object used for recomputation
- `chain_tx_hash`: nullable field reserved for the Polygon transaction hash

The hash algorithm is deliberately the PRD formula with no separators:

```text
SHA-256(image bytes || matched URL UTF-8 || fingerprint timestamp UTF-8)
```

The blockchain implementation must use the already stored `sha256_hash`; it
should not generate a new timestamp or normalize the URL.

## Tests

Tests avoid live API calls and credentials:

```powershell
python -m unittest discover -s tests -v
```

They cover canonical fingerprinting, URL normalization, cross-provider result
merging, deduplication, and Google Vision response parsing.

## Known limitations

- Google Vision Web Detection primarily identifies matching or visually similar
  image pages; it is not a general facial-embedding search engine.
- Social platforms commonly block crawlers and direct image retrieval.
- Page metadata and matched-image retrieval are best-effort because source sites
  may require authentication, JavaScript, or anti-bot checks.
- Public figures generally produce more reliable web results than ordinary people.
- SFace and legacy dlib embeddings are not mutually comparable even though both
  contain 128 values; each record stores its embedding model in `metadata`.
- Local hash comparison detects changes within the Supabase evidence path but is
  not immutable proof. Blockchain anchoring is deferred to Phase 3.
- This is a hackathon testnet demonstration, not a production identity system.

Use only consented images or permissively licensed public-figure images. Do not
use this pipeline for stalking, harassment, access control, or high-impact
identity decisions.
