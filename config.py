"""Environment-based configuration for the CLI pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required pipeline configuration is absent."""


@dataclass(frozen=True, slots=True)
class Settings:
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_bucket: str = "face-evidence"
    supabase_table: str = "face_records"
    request_timeout_seconds: float = 15.0
    max_download_bytes: int = 15 * 1024 * 1024
    polygon_amoy_rpc_url: str | None = None
    blockchain_private_key: str | None = None
    contract_address: str | None = None
    polygon_chain_id: int = 80002

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            supabase_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "face-evidence"),
            supabase_table=os.getenv("SUPABASE_RECORDS_TABLE", "face_records"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")),
            max_download_bytes=min(
                int(os.getenv("MAX_DOWNLOAD_BYTES", str(15 * 1024 * 1024))),
                15 * 1024 * 1024,
            ),
            polygon_amoy_rpc_url=os.getenv("POLYGON_AMOY_RPC_URL"),
            blockchain_private_key=os.getenv("BLOCKCHAIN_PRIVATE_KEY"),
            contract_address=os.getenv("CONTRACT_ADDRESS"),
            polygon_chain_id=int(os.getenv("POLYGON_CHAIN_ID", "80002")),
        )

    def require_supabase(self) -> tuple[str, str]:
        url = self.supabase_url
        key = self.supabase_service_role_key
        missing = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if missing:
            raise ConfigurationError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        assert url is not None and key is not None
        return url, key
