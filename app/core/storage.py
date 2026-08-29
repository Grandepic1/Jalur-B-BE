from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings


class EvidenceStorage:
    def __init__(self) -> None:
        if not settings.evidence_storage_configured:
            raise RuntimeError("Evidence attachment storage is not configured")
        self.bucket = settings.supabase_storage_bucket
        self.client: BaseClient = boto3.client(
            "s3",
            endpoint_url=settings.supabase_storage_endpoint,
            region_name=settings.supabase_storage_region,
            aws_access_key_id=settings.supabase_storage_access_key_id,
            aws_secret_access_key=settings.supabase_storage_secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_download_url(self, key: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=900,
        )


@lru_cache
def get_evidence_storage() -> EvidenceStorage:
    return EvidenceStorage()
