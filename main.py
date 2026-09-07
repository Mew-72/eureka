"""CLI entry point for the end-to-end Face ID + Blockchain Verification pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from blockchain.blockchain_pipeline import verify_on_chain, write_to_blockchain
from config import ConfigurationError, Settings
from content_fetch import ContentFetcher
from face_encoding import EMBEDDING_MODEL, FaceEncodingError, encode_single_face
from fingerprinting import compute_fingerprint, utc_now_iso
from search.merge_results import merge_and_rank
from search.pimeyes_scraper import search_pimeyes
from search.vision_search import VisionSearchError, search_web
from storage.supabase_pipeline import SupabasePipeline, SupabaseStorageError

LOGGER = logging.getLogger("face_pipeline")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Identify a face on the web and anchor tamper-evident evidence to a blockchain."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full end-to-end pipeline")
    run_parser.add_argument("image", type=Path, help="Path to a single-face image")
    run_parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum ranked results to retain (default: 20)",
    )
    run_parser.add_argument(
        "--confirm-authorized-use",
        action="store_true",
        help="Confirm the image is consented or a permissively licensed public figure",
    )
    run_parser.add_argument(
        "--json", action="store_true", help="Print the final result as JSON"
    )

    verify_local_parser = subparsers.add_parser(
        "verify-local", help="Recompute a stored fingerprint locally"
    )
    verify_local_parser.add_argument("record_id", help="Face record UUID")
    verify_local_parser.add_argument(
        "--json", action="store_true", help="Print verification as JSON"
    )

    verify_chain_parser = subparsers.add_parser(
        "verify-onchain", help="Verify record hash against Polygon Amoy / EVM smart contract"
    )
    verify_chain_parser.add_argument("record_id", help="Face record UUID")
    verify_chain_parser.add_argument("expected_hash", help="SHA-256 fingerprint hash")
    verify_chain_parser.add_argument(
        "--json", action="store_true", help="Print on-chain verification as JSON"
    )
    return parser


def run_pipeline(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    if not args.confirm_authorized_use:
        raise ValueError(
            "Refusing biometric search without --confirm-authorized-use"
        )
    if args.max_results < 1 or args.max_results > 100:
        raise ValueError("--max-results must be between 1 and 100")

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise ValueError(f"Input image does not exist: {image_path}")

    LOGGER.info("[1/7] Reading probe image")
    probe_bytes = image_path.read_bytes()
    if len(probe_bytes) > settings.max_download_bytes:
        raise ValueError(
            f"Probe image exceeds the {settings.max_download_bytes}-byte upload limit"
        )

    LOGGER.info("[2/7] Detecting and encoding one face with YuNet + SFace")
    embedding = encode_single_face(image_path)
    LOGGER.info("Generated %d-dimensional face embedding", len(embedding))

    LOGGER.info("[3/7] Searching open web & social media (Google Vision + PimEyes)")
    vision_results = []
    try:
        vision_results = search_web(image_path, max_results=args.max_results)
        LOGGER.info("Google Vision Web Detection returned %d results", len(vision_results))
    except VisionSearchError as exc:
        LOGGER.warning("Google Vision search error: %s", exc)

    pimeyes_results = search_pimeyes(image_path, max_results=args.max_results)
    if pimeyes_results:
        LOGGER.info("PimEyes facial search returned %d results", len(pimeyes_results))

    ranked_results = merge_and_rank(vision_results, pimeyes_results)
    if not ranked_results:
        raise ValueError("No matching web or social media posts found across providers")

    selected = ranked_results[0]
    LOGGER.info(
        "Selected top-ranked match: %s (source=%s, match_type=%s, score=%.4f)",
        selected.page_url,
        selected.source,
        selected.match_type,
        selected.score,
    )

    LOGGER.info("[4/7] Fetching selected content and page metadata")
    fetcher = ContentFetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_download_bytes=settings.max_download_bytes,
    )
    content = fetcher.fetch(selected)

    LOGGER.info("[5/7] Computing canonical SHA-256 fingerprint")
    if content.image_bytes is not None:
        fingerprint_bytes = content.image_bytes
        fingerprint_image_source = "matched"
    else:
        fingerprint_bytes = probe_bytes
        fingerprint_image_source = "probe"
        LOGGER.warning(
            "Matched image could not be downloaded; fingerprinting probe image with page URL"
        )
    fingerprint_timestamp = utc_now_iso()
    sha256_hash = compute_fingerprint(
        fingerprint_bytes, selected.page_url, fingerprint_timestamp
    )
    LOGGER.info("SHA-256 Fingerprint: %s", sha256_hash)

    LOGGER.info("[6/7] Storing evidence record in Supabase / Local storage")
    record_id = str(uuid4())
    supabase_saved = False
    try:
        settings.require_supabase()
        storage = SupabasePipeline(settings)
        record = storage.save_record(
            probe_path=image_path,
            probe_bytes=probe_bytes,
            embedding=embedding,
            embedding_model=EMBEDDING_MODEL,
            selected_result=selected,
            content=content,
            fingerprint_timestamp=fingerprint_timestamp,
            sha256_hash=sha256_hash,
            fingerprint_image_source=fingerprint_image_source,
            vision_result_count=len(ranked_results),
        )
        record_id = record["id"]
        supabase_saved = True
        LOGGER.info("Evidence stored in Supabase with record ID: %s", record_id)
    except ConfigurationError as exc:
        LOGGER.warning("Supabase not configured (%s); evidence recorded locally.", exc)
    except SupabaseStorageError as exc:
        LOGGER.warning("Supabase storage error (%s); evidence recorded locally.", exc)

    LOGGER.info("[7/7] Anchoring record hash to Blockchain (Polygon Amoy / EVM)")
    blockchain_res = write_to_blockchain(
        record_id=record_id,
        sha256_hash=sha256_hash,
        matched_url=selected.page_url,
        settings=settings,
    )
    tx_hash = blockchain_res.get("tx_hash")
    LOGGER.info(
        "Blockchain anchor successful. Tx Hash: %s (Network: %s)",
        tx_hash,
        blockchain_res.get("network"),
    )

    return {
        "record_id": record_id,
        "embedding_model": EMBEDDING_MODEL,
        "matched_url": selected.page_url,
        "matched_image_url": selected.image_url,
        "match_source": selected.source,
        "match_type": selected.match_type,
        "ranking_score": selected.score,
        "sha256_hash": sha256_hash,
        "fingerprint_timestamp": fingerprint_timestamp,
        "fingerprint_image_source": fingerprint_image_source,
        "total_results_found": len(ranked_results),
        "supabase_persisted": supabase_saved,
        "blockchain_tx_hash": tx_hash,
        "blockchain_network": blockchain_res.get("network"),
        "blockchain_status": blockchain_res.get("status", "anchored"),
    }


def verify_local_record(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Retrieving stored evidence and recomputing local SHA-256")
    result = SupabasePipeline(settings).verify_local(args.record_id)
    return asdict(result)


def verify_blockchain_record(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Querying blockchain smart contract for record %s", args.record_id)
    result = verify_on_chain(args.record_id, args.expected_hash, settings)
    return asdict(result)


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print("\n" + "=" * 50)
    print("PIPELINE EXECUTION RESULT")
    print("=" * 50)
    for key, value in result.items():
        print(f"{key:<28}: {value}")
    print("=" * 50)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        settings = Settings.from_env()
        if args.command == "run":
            result = run_pipeline(args, settings)
        elif args.command == "verify-local":
            result = verify_local_record(args, settings)
        elif args.command == "verify-onchain":
            result = verify_blockchain_record(args, settings)
        else:
            parser.print_help()
            return 1

        _print_result(result, args.json)

        if args.command == "verify-local" and not result.get("matches"):
            return 2
        if args.command == "verify-onchain" and not result.get("matches"):
            return 2
        return 0

    except (
        ConfigurationError,
        FaceEncodingError,
        SupabaseStorageError,
        VisionSearchError,
        OSError,
        ValueError,
    ) as exc:
        LOGGER.error("Pipeline failure: %s", exc)
        if args.verbose:
            LOGGER.exception("Pipeline failure details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
