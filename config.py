"""Environment-based configuration for the CLI pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required pipeline configuration is absent."""


def _environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_bucket: str = "face-evidence"
    supabase_table: str = "face_records"
    request_timeout_seconds: float = 15.0
    max_download_bytes: int = 15 * 1024 * 1024
    pimeyes_timeout_seconds: float = 30.0
    pimeyes_headless: bool = True
    polygon_rpc_url: str | None = None
    polygon_private_key: str | None = None
    face_record_contract_address: str | None = None
    polygon_chain_id: int = 80002
    blockchain_confirmation_timeout_seconds: float = 120.0

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
            pimeyes_timeout_seconds=float(
                os.getenv("PIMEYES_TIMEOUT_SECONDS", "30")
            ),
            pimeyes_headless=_environment_bool("PIMEYES_HEADLESS", True),
            polygon_rpc_url=os.getenv("POLYGON_RPC_URL"),
            polygon_private_key=os.getenv("POLYGON_PRIVATE_KEY"),
            face_record_contract_address=os.getenv("FACE_RECORD_CONTRACT_ADDRESS"),
            polygon_chain_id=int(os.getenv("POLYGON_CHAIN_ID", "80002")),
            blockchain_confirmation_timeout_seconds=float(
                os.getenv("BLOCKCHAIN_CONFIRMATION_TIMEOUT_SECONDS", "120")
            ),
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

    def require_blockchain_reader(self) -> tuple[str, str]:
        missing = []
        if not self.polygon_rpc_url:
            missing.append("POLYGON_RPC_URL")
        if not self.face_record_contract_address:
            missing.append("FACE_RECORD_CONTRACT_ADDRESS")
        if missing:
            raise ConfigurationError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        assert self.polygon_rpc_url is not None
        assert self.face_record_contract_address is not None
        return self.polygon_rpc_url, self.face_record_contract_address

    def require_blockchain_writer(self) -> tuple[str, str, str]:
        rpc_url, contract_address = self.require_blockchain_reader()
        if not self.polygon_private_key:
            raise ConfigurationError(
                "Missing required environment variable: POLYGON_PRIVATE_KEY"
            )
        return rpc_url, contract_address, self.polygon_private_key

    def require_blockchain_deployer(self) -> tuple[str, str]:
        missing = []
        if not self.polygon_rpc_url:
            missing.append("POLYGON_RPC_URL")
        if not self.polygon_private_key:
            missing.append("POLYGON_PRIVATE_KEY")
        if missing:
            raise ConfigurationError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        assert self.polygon_rpc_url is not None
        assert self.polygon_private_key is not None
        return self.polygon_rpc_url, self.polygon_private_key
