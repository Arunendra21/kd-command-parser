"""Small helpers around boto3 for the SeaweedFS S3 API."""
import os

import boto3


def client(endpoint=None):
    return boto3.client("s3", endpoint_url=endpoint or os.environ["S3_ENDPOINT"])


def get_text(s3, bucket, key):
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")


def put_text(s3, bucket, key, text):
    s3.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))


def exists(s3, bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False


def list_keys(s3, bucket, prefix):
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    return sorted(keys)
