"""CLI entry point for Phase 1 of the face identification pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import ConfigurationError, Settings
from content_fetch import ContentFetcher
from face_encoding import EMBEDDING_MODEL, FaceEncodingError, encode_single_face
from fingerprinting import compute_fingerprint, utc_now_iso
from search.merge_results import merge_and_rank
from search.vision_search import VisionSearchError, search_web
from storage.supabase_pipeline import SupabasePipeline, SupabaseStorageError

LOGGER = logging.getLogger("face_pipeline")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Identify a face on the web and persist verifiable evidence."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the Phase 1 pipeline")
    run_parser.add_argument("image", type=Path, help="Path to a single-face image")
    run_parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum ranked Google Vision results to retain (default: 20)",
    )
    run_parser.add_argument(
        "--confirm-authorized-use",
        action="store_true",
        help="Confirm the image is consented or a permissively licensed public figure",
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
    return parser


def run_pipeline(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    if not args.confirm_authorized_use:
        raise ValueError(
            "Refusing biometric search without --confirm-authorized-use"
        )
    if args.max_results < 1 or args.max_results > 100:
        raise ValueError("--max-results must be between 1 and 100")

    # Fail before processing or sharing biometric data if persistence cannot run.
    settings.require_supabase()

    image_path = args.image.expanduser().resolve()
    if not image_path.is_file():
        raise ValueError(f"Input image does not exist: {image_path}")

    LOGGER.info("[1/6] Reading probe image")
    probe_bytes = image_path.read_bytes()
    if len(probe_bytes) > settings.max_download_bytes:
        raise ValueError(
            f"Probe image exceeds the {settings.max_download_bytes}-byte "
            "Supabase Storage limit"
        )

    LOGGER.info("[2/6] Detecting and encoding one face")
    embedding = encode_single_face(image_path)
    LOGGER.info("Generated %d-dimensional face embedding", len(embedding))

    LOGGER.info("[3/6] Searching Google Vision Web Detection")
    vision_results = search_web(image_path, max_results=args.max_results)
    ranked_results = merge_and_rank(vision_results)
    selected = ranked_results[0]
    LOGGER.info(
        "Selected %s result (type=%s, ranking_score=%.4f)",
        selected.page_url,
        selected.match_type,
        selected.score,
    )

    LOGGER.info("[4/6] Fetching selected content and page metadata")
    fetcher = ContentFetcher(
        timeout_seconds=settings.request_timeout_seconds,
        max_download_bytes=settings.max_download_bytes,
    )
    content = fetcher.fetch(selected)

    LOGGER.info("[5/6] Computing canonical SHA-256 fingerprint")
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

    LOGGER.info("[6/6] Uploading evidence and inserting Supabase record")
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
        "vision_result_count": len(ranked_results),
        "blockchain_status": "pending_phase_3",
    }


def verify_record(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    LOGGER.info("Retrieving stored evidence and recomputing SHA-256")
    result = SupabasePipeline(settings).verify_local(args.record_id)
    return asdict(result)


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
        else:
            result = verify_record(args, settings)
        _print_result(result, args.json)
        if args.command == "verify-local" and not result["matches"]:
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
        LOGGER.error("%s", exc)
        if args.verbose:
            LOGGER.exception("Pipeline failure details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
