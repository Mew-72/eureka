"""CLI entry point for the face identification pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

from blockchain.client import BlockchainClient, BlockchainError
from blockchain.local import LocalBlockchainSession
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
        description="Identify a face on the web and persist verifiable evidence."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the search pipeline")
    run_parser.add_argument("image", type=Path, help="Path to a single-face image")
    run_parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum ranked search results to retain (default: 20)",
    )
    run_parser.add_argument(
        "--confirm-authorized-use",
        action="store_true",
        help="Confirm the image is consented or a permissively licensed public figure",
    )
    run_parser.add_argument(
        "--use-pimeyes",
        action="store_true",
        help=(
            "Upload the probe to PimEyes under its current terms and merge any "
            "exposed source URLs"
        ),
    )
    run_parser.add_argument(
        "--show-pimeyes-browser",
        action="store_true",
        help="Show Chrome during PimEyes automation (requires --use-pimeyes)",
    )
    run_parser.add_argument(
        "--local-chain",
        action="store_true",
        help="Anchor and immediately verify on an ephemeral Ethereum test chain",
    )
    run_parser.add_argument(
        "--skip-blockchain",
        action="store_true",
        help="Persist evidence without anchoring it on Polygon",
    )
    run_parser.add_argument(
        "--json", action="store_true", help="Print the final result as JSON"
    )

    verify_parser = subparsers.add_parser(
        "verify-local", help="Recompute a stored fingerprint without blockchain"
    )
    verify_parser.add_argument("record_id", help="Supabase face_records UUID")
    verify_parser.add_argument(
        "--json", action="store_true", help="Print verification as JSON"
    )

    anchor_parser = subparsers.add_parser(
        "anchor", help="Anchor an existing Supabase record on Polygon"
    )
    anchor_parser.add_argument("record_id", help="Supabase face_records UUID")
    anchor_parser.add_argument(
        "--json", action="store_true", help="Print the transaction as JSON"
    )

    chain_verify_parser = subparsers.add_parser(
        "verify", help="Verify stored evidence against the Polygon contract"
    )
    chain_verify_parser.add_argument("record_id", help="Supabase face_records UUID")
    chain_verify_parser.add_argument(
        "--json", action="store_true", help="Print verification as JSON"
    )
    return parser


def run_pipeline(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    if not args.confirm_authorized_use:
        raise ValueError(
            "Refusing biometric search without --confirm-authorized-use"
        )
    if args.max_results < 1 or args.max_results > 100:
        raise ValueError("--max-results must be between 1 and 100")
    if args.show_pimeyes_browser and not args.use_pimeyes:
        raise ValueError("--show-pimeyes-browser requires --use-pimeyes")
    if args.local_chain and args.skip_blockchain:
        raise ValueError("--local-chain cannot be combined with --skip-blockchain")

    # Fail before processing or sharing biometric data if persistence cannot run.
    settings.require_supabase()
    if not args.skip_blockchain and not args.local_chain:
        settings.require_blockchain_writer()

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise ValueError(f"Input image does not exist: {image_path}")

    total_stages = 6 if args.skip_blockchain else 7
    LOGGER.info("[1/%d] Reading probe image", total_stages)
    probe_bytes = image_path.read_bytes()
    if len(probe_bytes) > settings.max_download_bytes:
        raise ValueError(
            f"Probe image exceeds the {settings.max_download_bytes}-byte "
            "Supabase Storage limit"
        )

    LOGGER.info("[2/%d] Detecting and encoding one face", total_stages)
    embedding = encode_single_face(image_path)
    LOGGER.info("Generated %d-dimensional face embedding", len(embedding))

    pimeyes_results = []
    if args.use_pimeyes:
        LOGGER.info(
            "[3/%d] Searching Google Vision and PimEyes in parallel", total_stages
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            vision_future = executor.submit(
                search_web, image_path, max_results=args.max_results
            )
            pimeyes_future = executor.submit(
                search_pimeyes,
                image_path,
                max_results=args.max_results,
                timeout_seconds=settings.pimeyes_timeout_seconds,
                headless=(
                    settings.pimeyes_headless and not args.show_pimeyes_browser
                ),
            )
            vision_results = vision_future.result()
            pimeyes_results = pimeyes_future.result()
    else:
        LOGGER.info("[3/%d] Searching Google Vision Web Detection", total_stages)
        vision_results = search_web(image_path, max_results=args.max_results)

    ranked_results = merge_and_rank(vision_results, pimeyes_results)[
        : args.max_results
    ]
    selected = ranked_results[0]
    LOGGER.info(
        "Selected %s result (type=%s, ranking_score=%.4f)",
        selected.page_url,
        selected.match_type,
        selected.score,
    )

    LOGGER.info(
        "[4/%d] Fetching selected content and page metadata", total_stages
    )
    fetcher = ContentFetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_download_bytes=settings.max_download_bytes,
    )
    content = fetcher.fetch(selected)

    LOGGER.info("[5/%d] Computing canonical SHA-256 fingerprint", total_stages)
    if content.image_bytes is not None:
        fingerprint_bytes = content.image_bytes
        fingerprint_image_source = "matched"
    else:
        fingerprint_bytes = probe_bytes
        fingerprint_image_source = "probe"
        LOGGER.warning(
            "Matched image could not be downloaded; fingerprinting the stored probe "
            "image with the discovered page URL"
        )
    fingerprint_timestamp = utc_now_iso()
    sha256_hash = compute_fingerprint(
        fingerprint_bytes, selected.page_url, fingerprint_timestamp
    )

    LOGGER.info(
        "[6/%d] Uploading evidence and inserting Supabase record", total_stages
    )
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
        vision_result_count=len(vision_results),
        pimeyes_result_count=len(pimeyes_results),
        pimeyes_attempted=args.use_pimeyes,
    )

    LOGGER.info("Supabase record ID: %s", record["id"])
    transaction_hash = None
    block_number = None
    blockchain_status = "skipped"
    blockchain_network = None
    blockchain_verified = False
    if args.local_chain:
        LOGGER.info("[7/7] Writing to the local Ethereum chain and re-verifying")
        local_result = LocalBlockchainSession().anchor_and_verify(
            str(record["id"]), sha256_hash, selected.page_url
        )
        transaction_hash = local_result.transaction_hash
        block_number = local_result.block_number
        verification = storage.verify_local(str(record["id"]))
        blockchain_verified = (
            local_result.verified
            and verification.matches
            and verification.recomputed_hash == local_result.content_hash
            and verification.matched_url == local_result.source_url
        )
        if not blockchain_verified:
            raise BlockchainError(
                "Recomputed Supabase evidence did not match the local chain"
            )
        blockchain_status = "anchored_and_verified"
        blockchain_network = local_result.chain
    elif not args.skip_blockchain:
        LOGGER.info("[7/7] Anchoring fingerprint on Polygon")
        anchor_result = BlockchainClient(settings, require_signer=True).anchor(
            str(record["id"]), sha256_hash, selected.page_url
        )
        transaction_hash = anchor_result.transaction_hash
        block_number = anchor_result.block_number
        blockchain_network = f"Polygon chain {settings.polygon_chain_id}"
        if transaction_hash:
            storage.save_chain_tx_hash(str(record["id"]), transaction_hash)
        blockchain_status = (
            "already_anchored" if anchor_result.already_anchored else "anchored"
        )

    return {
        "record_id": record["id"],
        "embedding_model": EMBEDDING_MODEL,
        "matched_url": selected.page_url,
        "matched_image_url": selected.image_url,
        "match_source": selected.source,
        "match_type": selected.match_type,
        "ranking_score": selected.score,
        "sha256_hash": sha256_hash,
        "fingerprint_timestamp": fingerprint_timestamp,
        "fingerprint_image_source": fingerprint_image_source,
        "vision_result_count": len(vision_results),
        "pimeyes_result_count": len(pimeyes_results),
        "search_result_count": len(ranked_results),
        "blockchain_status": blockchain_status,
        "blockchain_network": blockchain_network,
        "blockchain_verified": blockchain_verified,
        "chain_tx_hash": transaction_hash,
        "chain_block_number": block_number,
    }


def verify_record(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Retrieving stored evidence and recomputing SHA-256")
    result = SupabasePipeline(settings).verify_local(args.record_id)
    return asdict(result)


def anchor_record(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Retrieving the stored fingerprint and source URL")
    storage = SupabasePipeline(settings)
    payload = storage.get_anchor_payload(args.record_id)
    LOGGER.info("Submitting the fingerprint to Polygon")
    result = BlockchainClient(settings, require_signer=True).anchor(
        payload.record_id, payload.sha256_hash, payload.matched_url
    )
    if result.transaction_hash:
        storage.save_chain_tx_hash(payload.record_id, result.transaction_hash)
    output = asdict(result)
    if output["transaction_hash"] is None:
        output["transaction_hash"] = payload.chain_tx_hash
    return output


def verify_on_chain(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Recomputing stored evidence and reading the Polygon contract")
    local = SupabasePipeline(settings).verify_local(args.record_id)
    on_chain = BlockchainClient(settings).get_record(args.record_id)
    hash_matches = on_chain.content_hash == local.recomputed_hash
    source_url_matches = on_chain.source_url == local.matched_url
    verified = local.matches and hash_matches and source_url_matches
    return {
        "record_id": local.record_id,
        "stored_hash": local.stored_hash,
        "recomputed_hash": local.recomputed_hash,
        "on_chain_hash": on_chain.content_hash,
        "stored_hash_matches_recomputed": local.matches,
        "recomputed_hash_matches_on_chain": hash_matches,
        "source_url_matches_on_chain": source_url_matches,
        "verified": verified,
        "matched_url": local.matched_url,
        "on_chain_source_url": on_chain.source_url,
        "chain_tx_hash": local.chain_tx_hash,
        "anchored_at": on_chain.anchored_at,
        "submitter": on_chain.submitter,
    }


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    for key, value in result.items():
        print(f"{key}: {value}")


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
            result = verify_record(args, settings)
        elif args.command == "anchor":
            result = anchor_record(args, settings)
        else:
            result = verify_on_chain(args, settings)
        _print_result(result, args.json)
        if args.command == "verify-local" and not result["matches"]:
            return 2
        if args.command == "verify" and not result["verified"]:
            return 2
        return 0
    except (
        BlockchainError,
        ConfigurationError,
        FaceEncodingError,
        SupabaseStorageError,
        VisionSearchError,
        OSError,
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        if args.verbose:
            LOGGER.exception("Pipeline failure details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
