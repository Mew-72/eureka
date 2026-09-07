"""Supabase Storage and Postgres persistence for pipeline evidence."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from config import Settings
from fingerprinting import compute_fingerprint
from models import ContentEvidence, SearchResult

LOGGER = logging.getLogger(__name__)


class SupabaseStorageError(RuntimeError):
    """Raised when evidence cannot be persisted or retrieved."""


@dataclass(frozen=True, slots=True)
class VerificationResult:
    record_id: str
    stored_hash: str
    recomputed_hash: str
    matches: bool
    image_source: str
    matched_url: str
    chain_tx_hash: str | None


@dataclass(frozen=True, slots=True)
class AnchorPayload:
    record_id: str
    sha256_hash: str
    matched_url: str
    chain_tx_hash: str | None


class SupabasePipeline:
    def __init__(self, settings: Settings):
        url, key = settings.require_supabase()
        try:
            from supabase import create_client
        except ImportError as exc:  # pragma: no cover - installation dependent
            raise SupabaseStorageError(
                "supabase is not installed; install requirements.txt"
            ) from exc

        self.client = create_client(url, key)
        self.bucket = settings.supabase_bucket
        self.table = settings.supabase_table
        self.max_upload_bytes = settings.max_download_bytes

    def save_record(
        self,
        *,
        probe_path: Path,
        probe_bytes: bytes,
        embedding: list[float],
        embedding_model: str,
        selected_result: SearchResult,
        content: ContentEvidence,
        fingerprint_timestamp: str,
        sha256_hash: str,
        fingerprint_image_source: str,
        vision_result_count: int,
        pimeyes_result_count: int = 0,
        pimeyes_attempted: bool = False,
    ) -> dict[str, Any]:
        record_id = str(uuid4())
        prefix = f"records/{record_id}"
        probe_storage_path = f"{prefix}/probe{probe_path.suffix.lower() or '.jpg'}"
        content_storage_path: str | None = None
        uploaded: list[str] = []

        try:
            self._upload(
                probe_storage_path,
                probe_bytes,
                mimetypes.guess_type(probe_path.name)[0] or "application/octet-stream",
            )
            uploaded.append(probe_storage_path)

            if content.image_bytes is not None:
                extension = mimetypes.guess_extension(
                    content.image_content_type or "image/jpeg"
                ) or ".jpg"
                content_storage_path = f"{prefix}/matched{extension}"
                self._upload(
                    content_storage_path,
                    content.image_bytes,
                    content.image_content_type or "image/jpeg",
                )
                uploaded.append(content_storage_path)
        except Exception as exc:
            self._remove_uploads(uploaded)
            if isinstance(exc, SupabaseStorageError):
                raise
            raise SupabaseStorageError("Failed to upload pipeline evidence") from exc

        fingerprint_storage_path = (
            content_storage_path
            if fingerprint_image_source == "matched"
            else probe_storage_path
        )
        if not fingerprint_storage_path:
            self._remove_uploads(uploaded)
            raise SupabaseStorageError("Fingerprint image was not uploaded")

        row = {
            "id": record_id,
            "fingerprint_timestamp": fingerprint_timestamp,
            "probe_storage_path": probe_storage_path,
            "content_storage_path": content_storage_path,
            "fingerprint_storage_path": fingerprint_storage_path,
            "fingerprint_image_source": fingerprint_image_source,
            "face_embedding": _vector_literal(embedding),
            "sha256_hash": sha256_hash,
            "matched_url": selected_result.page_url,
            "matched_image_url": selected_result.image_url,
            "match_source": selected_result.source,
            "match_type": selected_result.match_type,
            "match_score": selected_result.score,
            "page_title": content.page_title,
            "caption": content.caption,
            "platform": content.platform,
            "published_at": content.published_at,
            "vision_result_count": vision_result_count,
            "chain_tx_hash": None,
            "metadata": {
                "phase": 2 if pimeyes_attempted else 1,
                "embedding_model": embedding_model,
                "search_provider_counts": {
                    "google_vision": vision_result_count,
                    "pimeyes": pimeyes_result_count,
                },
                "pimeyes_attempted": pimeyes_attempted,
            },
        }
        try:
            response = self.client.table(self.table).insert(row).execute()
            data = getattr(response, "data", None)
            if not data:
                raise SupabaseStorageError("Supabase insert returned no record")
            return dict(data[0])
        except Exception as exc:
            # The insert may already have committed if the response was interrupted.
            # Keep evidence objects to avoid leaving a committed row with broken paths.
            if isinstance(exc, SupabaseStorageError):
                raise
            raise SupabaseStorageError(
                f"Failed to insert record {record_id}; evidence remains under {prefix}"
            ) from exc

    def get_anchor_payload(self, record_id: str) -> AnchorPayload:
        self._validate_record_id(record_id)
        try:
            response = (
                self.client.table(self.table)
                .select("id,sha256_hash,matched_url,chain_tx_hash")
                .eq("id", record_id)
                .single()
                .execute()
            )
            row = response.data
            return AnchorPayload(
                record_id=str(row["id"]),
                sha256_hash=str(row["sha256_hash"]),
                matched_url=str(row["matched_url"]),
                chain_tx_hash=(
                    str(row["chain_tx_hash"]) if row.get("chain_tx_hash") else None
                ),
            )
        except Exception as exc:
            raise SupabaseStorageError(
                f"Failed to retrieve anchor payload for {record_id}"
            ) from exc

    def save_chain_tx_hash(self, record_id: str, transaction_hash: str) -> None:
        self._validate_record_id(record_id)
        try:
            response = (
                self.client.table(self.table)
                .update({"chain_tx_hash": transaction_hash})
                .eq("id", record_id)
                .execute()
            )
            if not getattr(response, "data", None):
                raise SupabaseStorageError(
                    f"Supabase update returned no record for {record_id}"
                )
        except Exception as exc:
            if isinstance(exc, SupabaseStorageError):
                raise
            raise SupabaseStorageError(
                f"Transaction {transaction_hash} succeeded, but its hash could not "
                f"be saved for record {record_id}"
            ) from exc

    def verify_local(self, record_id: str) -> VerificationResult:
        self._validate_record_id(record_id)

        try:
            response = (
                self.client.table(self.table)
                .select(
                    "id,sha256_hash,matched_url,fingerprint_timestamp,"
                    "fingerprint_storage_path,fingerprint_image_source,chain_tx_hash"
                )
                .eq("id", record_id)
                .single()
                .execute()
            )
            row = response.data
            image_bytes = self.client.storage.from_(self.bucket).download(
                row["fingerprint_storage_path"]
            )
            recomputed = compute_fingerprint(
                bytes(image_bytes), row["matched_url"], row["fingerprint_timestamp"]
            )
        except Exception as exc:
            raise SupabaseStorageError(
                f"Failed to retrieve verification evidence for {record_id}"
            ) from exc

        stored = str(row["sha256_hash"])
        return VerificationResult(
            record_id=record_id,
            stored_hash=stored,
            recomputed_hash=recomputed,
            matches=stored == recomputed,
            image_source=str(row["fingerprint_image_source"]),
            matched_url=str(row["matched_url"]),
            chain_tx_hash=(
                str(row["chain_tx_hash"]) if row.get("chain_tx_hash") else None
            ),
        )

    @staticmethod
    def _validate_record_id(record_id: str) -> None:
        try:
            UUID(record_id)
        except ValueError as exc:
            raise SupabaseStorageError("Record ID must be a valid UUID") from exc

    def _upload(self, path: str, content: bytes, content_type: str) -> None:
        if len(content) > self.max_upload_bytes:
            raise SupabaseStorageError(
                f"Evidence object exceeds the {self.max_upload_bytes}-byte upload limit"
            )
        self.client.storage.from_(self.bucket).upload(
            path,
            content,
            file_options={"content-type": content_type, "upsert": "false"},
        )

    def _remove_uploads(self, paths: list[str]) -> None:
        if not paths:
            return
        try:
            self.client.storage.from_(self.bucket).remove(paths)
        except Exception as cleanup_error:
            LOGGER.warning(
                "Failed to remove partial Supabase uploads: %s", cleanup_error
            )


def _vector_literal(embedding: list[float]) -> str:
    if len(embedding) != 128:
        raise SupabaseStorageError(
            f"Expected a 128-dimensional embedding, received {len(embedding)}"
        )
    return "[" + ",".join(format(value, ".17g") for value in embedding) + "]"
