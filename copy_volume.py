import json
import os
from pathlib import Path

import boto3


SOURCE_BUCKET = os.environ["SOURCE_BUCKET"]
SOURCE_ENDPOINT = os.environ["SOURCE_ENDPOINT"]
SOURCE_REGION = os.environ["SOURCE_REGION"]
DESTINATION = Path(os.environ.get("DESTINATION", "/workspace")).resolve()
SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX", "heartlib/")


def main():
    client = boto3.client(
        "s3",
        endpoint_url=SOURCE_ENDPOINT,
        region_name=SOURCE_REGION,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    paginator = client.get_paginator("list_objects_v2")
    copied = 0
    copied_bytes = 0

    for page in paginator.paginate(Bucket=SOURCE_BUCKET, Prefix=SOURCE_PREFIX):
        for item in page.get("Contents", []):
            key = item["Key"]
            target = (DESTINATION / key).resolve()
            if DESTINATION not in target.parents and target != DESTINATION:
                raise RuntimeError(f"Unsafe object key: {key}")
            if key.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = int(item["Size"])
            if target.exists() and target.stat().st_size == expected:
                copied += 1
                copied_bytes += expected
                continue
            client.download_file(SOURCE_BUCKET, key, str(target))
            if target.stat().st_size != expected:
                raise RuntimeError(f"Size mismatch after copying {key}")
            copied += 1
            copied_bytes += expected
            print(f"copied {copied}: {key} ({expected} bytes)", flush=True)

    result = {"objects": copied, "bytes": copied_bytes, "source": SOURCE_BUCKET}
    (DESTINATION / ".migration-complete.json").write_text(
        json.dumps(result, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
