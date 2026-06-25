"""B2 (S3) access for the audiobook domain.

Lives in repo/ alongside b2_client (boto3 stays contained here). All calls go
through the single shared S3 client built in b2_client.get_s3_client(), so the
custom user agent + signature config are inherited automatically.
"""

import io
import json

from botocore.exceptions import ClientError

from app.config import settings
from app.repo.b2_client import get_s3_client


def put_bytes(data: bytes, key: str, content_type: str) -> None:
    """Write raw bytes to a B2 key (chapter audio, master). Raises on failure."""
    client = get_s3_client()
    try:
        client.put_object(
            Bucket=settings.b2_bucket_name,
            Key=key,
            Body=io.BytesIO(data),
            ContentType=content_type,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 put failed for '{key}': {e}") from e


def read_object(key: str) -> bytes | None:
    """Read an object's bytes from B2. Returns None if it does not exist."""
    client = get_s3_client()
    try:
        response = client.get_object(Bucket=settings.b2_bucket_name, Key=key)
        return response["Body"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            return None
        raise RuntimeError(f"B2 read failed for '{key}': {e}") from e


def write_json(key: str, obj: dict) -> None:
    """Serialize a dict to JSON and store it at `key`."""
    body = json.dumps(obj, default=str).encode("utf-8")
    put_bytes(body, key, "application/json")


def read_json(key: str) -> dict | None:
    """Read and parse a JSON object from B2. Returns None if missing."""
    raw = read_object(key)
    if raw is None:
        return None
    return json.loads(raw)


def list_prefixes(
    prefix: str,
    limit: int | None = None,
    start_after: str | None = None,
) -> list[str]:
    """List immediate sub-prefixes under `prefix` (S3 Delimiter='/').

    Used to enumerate per-book folders under `audiobooks/`. Returns the full
    common-prefix strings (e.g. `audiobooks/<book-id>/`).
    """
    client = get_s3_client()
    prefixes: list[str] = []
    kwargs: dict = {
        "Bucket": settings.b2_bucket_name,
        "Prefix": prefix,
        "Delimiter": "/",
    }
    if start_after:
        kwargs["StartAfter"] = start_after
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            for cp in response.get("CommonPrefixes", []):
                prefixes.append(cp["Prefix"])
                if limit is not None and len(prefixes) >= limit:
                    return prefixes
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 list-prefixes failed for '{prefix}': {e}") from e
    return prefixes


def prefix_size(prefix: str) -> int:
    """Sum the bytes of every object under `prefix`."""
    client = get_s3_client()
    total = 0
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix}
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            total += sum(o["Size"] for o in response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 size query failed for '{prefix}': {e}") from e
    return total


def delete_prefix(prefix: str) -> int:
    """Delete every object under `prefix` via batched delete_objects.

    Returns the number of objects deleted. Used to remove an entire audiobook.
    """
    client = get_s3_client()
    deleted = 0
    kwargs: dict = {"Bucket": settings.b2_bucket_name, "Prefix": prefix}
    try:
        while True:
            response = client.list_objects_v2(**kwargs)
            objects = [{"Key": o["Key"]} for o in response.get("Contents", [])]
            if objects:
                client.delete_objects(
                    Bucket=settings.b2_bucket_name,
                    Delete={"Objects": objects, "Quiet": True},
                )
                deleted += len(objects)
            if not response.get("IsTruncated"):
                break
            kwargs["ContinuationToken"] = response["NextContinuationToken"]
    except ClientError as e:
        raise RuntimeError(f"B2 delete-prefix failed for '{prefix}': {e}") from e
    return deleted


def get_stream_url(key: str, expires_in: int = 600) -> str:
    """Presigned GET URL WITHOUT forced-attachment disposition.

    Lets the browser stream chapter audio inline into an <audio> element,
    which exercises B2 HTTP Range reads. Raises RuntimeError on failure.
    """
    client = get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.b2_bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        raise RuntimeError(f"B2 stream-presign failed for '{key}': {e}") from e
