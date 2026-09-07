# Face Identification & Blockchain Verification
## Project Document & Product Requirements Document (PRD)
**Hackathon:** HH Goa 2026 — Shortlisting Task 3

---

## 1. Overview

### 1.1 What We're Building
An end-to-end pipeline that takes a face photo as input, finds a genuine, real-world social media/web post containing that face, and then anchors a tamper-evident, verifiable record of that discovered content on a blockchain. The system demonstrates three distinct technical capabilities chained together: **biometric identification → open-web/social search → cryptographic proof-of-integrity**.

### 1.2 Why This Project
The task tests whether a team can integrate three fundamentally different technology domains — computer vision, live web/OSINT search, and blockchain — into one working, demoable pipeline within a tight hackathon window. It mirrors a real, active problem space (deepfake verification, impersonation detection, digital identity proofing) rather than being a toy exercise, which is why we're building it as closely as possible to how production-grade OSINT/authenticity tools actually work rather than hardcoding any step.

### 1.3 Why Each Design Choice
- **Public figure as probe image (Elon Musk):** avoids consent/privacy issues of searching a random person's face, and dramatically improves match reliability since heavily-photographed public figures return far more consistent face-search hits than ordinary individuals, de-risking the live demo.
- **Dual search sources (Google Vision Web Detection + PimEyes):** Vision API is stable, rate-limit-friendly, and API-documented but only does exact-file image matching, missing most social platforms. PimEyes does true facial-embedding matching and reaches further into social/dating sites but is unofficial, CAPTCHA-prone, and rate-limited. Running both and merging results gives genuine redundancy — if one fails live, the other still produces a real result.
- **Supabase for storage:** Supabase natively supports `pgvector`, which is purpose-built for storing the 128-d face embeddings our face recognition step produces, alongside a Storage bucket for the raw image and a Postgres table for match metadata and hashes — avoiding the need for a separate vector DB or custom backend.
- **Public testnet blockchain (Polygon Amoy) over mainnet:** demonstrates the exact same verification mechanics as mainnet (deployed contract, real transaction, on-chain read-back) without spending real money or waiting on slow/expensive confirmations — appropriate for a demo, not a production identity system.
- **Hash-anchoring instead of storing raw data on-chain:** matches how existing image-authenticity projects (e.g., blockchain photo-validation tools) work — chains are expensive and public, so only a SHA-256 fingerprint of the image + matched URL + timestamp goes on-chain, while the actual content stays in Supabase. Verification means recomputing the hash and comparing it to the on-chain value.

---

## 2. Pipeline Architecture

```
[1] Face Scan Input (Elon Musk probe photo, sourced from Wikimedia Commons — CC licensed)
        │
        ▼
[2] Face Detection + Encoding
    - Library: OpenCV YuNet detector + SFace recognizer
    - Output: 128-dimensional SFace embedding
        │
        ▼
[3] Web / Social Media Search (run in parallel, then merge + dedup)
    ┌────────────────────────────┬─────────────────────────────────┐
    │ Google Cloud Vision         │ PimEyes (Selenium automation)   │
    │ Web Detection API           │                                  │
    │ - pagesWithMatchingImages   │ - True facial-embedding match   │
    │ - Stable, documented, free  │ - Reaches social/dating sites   │
    │   tier available            │ - Unofficial, CAPTCHA-prone,    │
    │                              │   rate-limited (~10/IP free)    │
    └────────────────────────────┴─────────────────────────────────┘
        │
        ▼  (pick top-scoring / highest-confidence real match URL)
[4] Content Fetch
    - Pull matched post's image + visible metadata (caption, platform, date)
        │
        ▼
[5] Storage (Supabase)
    - Storage bucket: raw probe image
    - Postgres table (pgvector): face_embedding, sha256_hash, matched_url,
      match_source, match_score, chain_tx_hash
        │
        ▼
[6] Fingerprinting
    - SHA-256( image_bytes + matched_url + timestamp )
        │
        ▼
[7] Blockchain Write (Polygon Amoy testnet via web3.py)
    - Smart contract: storeRecord(bytes32 hash, string sourceUrl)
    - Emits event, stores hash in on-chain mapping keyed by record ID
    - Returns transaction hash → saved back into Supabase row
        │
        ▼
[8] Verification (the demo's key moment)
    - Re-fetch stored image + metadata from Supabase
    - Recompute SHA-256 hash
    - Call contract.getHash(record_id) on-chain
    - Compare recomputed hash vs. on-chain hash → match/tamper result
```

---

## 3. Product Requirements Document (PRD)

### 3.1 Objective
Deliver a working, screen-recordable pipeline and public GitHub repository that satisfies all four HH Goa 2026 Task 3 requirements: genuine face-based web/social search, blockchain-anchored verification, no hosted website, and a complete README.

### 3.2 In Scope
- Face detection and 128-d encoding from a single input image.
- Live (non-hardcoded) search against Google Vision Web Detection and PimEyes.
- Deduplication/merge logic across both search sources, selecting one confirmed real matching post.
- Off-chain storage of image, embedding, and metadata in Supabase (Storage + Postgres/pgvector).
- SHA-256 fingerprinting of the matched content.
- Deployment of a minimal Solidity smart contract to Polygon Amoy testnet.
- On-chain write of the fingerprint via `web3.py`.
- On-chain re-verification step demonstrating tamper-evidence.
- CLI or minimal FastAPI endpoint set to run and demo the full flow (no hosted frontend required).
- GitHub repository with complete README (purpose, setup, blockchain used, limitations).
- Screen recording of an end-to-end run.

### 3.3 Out of Scope
- Any hosted/public-facing website or UI.
- Mainnet blockchain deployment.
- Support for arbitrary/unknown faces with guaranteed high match accuracy (explicitly a known limitation — see 3.7).
- Bulk/batch processing of multiple faces.
- Long-term production security hardening (key management, rate limiting, abuse prevention).

### 3.4 User Stories
- As a judge, I want to see a real face image go in and a real, verifiable social media post come out, so I can confirm the pipeline isn't faking its search step.
- As a judge, I want to see the discovered post's fingerprint written to a blockchain and then independently re-verified, so I can confirm the tamper-evidence claim is real, not simulated.
- As a reviewer of the GitHub repo, I want clear setup instructions and stated limitations, so I can run and evaluate the project without needing to guess at missing context.

### 3.5 Functional Requirements
| ID | Requirement | Priority |
|---|---|---|
| FR1 | System detects a face and generates a 128-d embedding from an input image | Must |
| FR2 | System queries Google Vision Web Detection API with the input image and returns real matching page URLs | Must |
| FR3 | System attempts a PimEyes search via automation and returns real matching page URLs when available | Must |
| FR4 | System merges and deduplicates results from both sources and selects the highest-confidence match | Must |
| FR5 | System stores the probe image, embedding, and match metadata in Supabase | Must |
| FR6 | System computes a SHA-256 hash of the matched content (image bytes + URL + timestamp) | Must |
| FR7 | System writes the hash and reference ID to a deployed smart contract on Polygon Amoy | Must |
| FR8 | System re-verifies stored data against the on-chain hash on demand | Must |
| FR9 | System falls back gracefully if PimEyes is rate-limited/CAPTCHA'd, still completing the pipeline via Vision API results | Should |
| FR10 | System logs each pipeline stage's output for demo narration | Should |

### 3.6 Non-Functional Requirements
- **Reliability:** the demo path must complete even if one search source fails (graceful degradation via FR9).
- **Cost:** total run cost should stay within free/low-cost tiers (Vision API free tier, Amoy testnet is gas-free via faucet, Supabase free tier).
- **Reproducibility:** a fresh clone of the repo plus documented API keys should reproduce the full pipeline end-to-end.
- **Ethical use:** probe images must be of consenting individuals or public figures with permissively-licensed photos (e.g., Wikimedia Commons).

### 3.7 Known Limitations (to state explicitly in README)
- Face-search APIs index the open web; most major platforms (Instagram, Facebook) block reverse-face-crawling directly, so matches skew toward X/Twitter, news, and blogs.
- PimEyes automation is inherently unstable (CAPTCHA, IP rate limits) and is best-effort, not guaranteed, in any single run.
- Match accuracy is significantly higher for well-photographed public figures than for ordinary individuals with limited online presence.
- The blockchain step proves the fingerprint hasn't changed since it was recorded; it does not prove the discovered post itself is authentic or unaltered at its source.
- This is a testnet demonstration, not a production identity-verification system.

### 3.8 Tech Stack Summary
| Layer | Choice |
|---|---|
| Face detection/encoding | OpenCV YuNet + SFace |
| Web search | Google Cloud Vision Web Detection API |
| Social search | PimEyes (Selenium automation) |
| Storage | Supabase (Storage bucket + Postgres/pgvector) |
| Hashing | SHA-256 (Python hashlib) |
| Blockchain | Polygon Amoy testnet, Solidity contract, web3.py |
| Interface | CLI / minimal FastAPI (no hosted frontend) |

### 3.9 Success Metrics
- Pipeline runs start-to-finish on at least one probe image with a genuinely discovered post.
- On-chain transaction hash is produced and independently re-verifiable during the recorded demo.
- README and repo satisfy all four stated submission requirements.
- Screen recording clearly shows each of the three pipeline stages executing live, not pre-recorded/edited results.



## 4. Repository Structure (Recommended)
```
/face-blockchain-verify
├── README.md
├── requirements.txt
├── face_encoding.py
├── search/
│   ├── vision_search.py
│   ├── pimeyes_scraper.py
│   └── merge_results.py
├── storage/
│   └── supabase_pipeline.py
├── blockchain/
│   ├── contracts/FaceRecord.sol
│   ├── deploy.py
│   └── verify.py
├── supabase_schema.sql
└── main.py   # orchestrates the full pipeline end-to-end
```
