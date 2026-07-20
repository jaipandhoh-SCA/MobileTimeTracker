import os
import re
import io
import boto3
from botocore.config import Config


def get_r2_client():
    """Get configured boto3 S3 client for Cloudflare R2."""
    return boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def _bucket():
    return os.environ['R2_BUCKET']


def sanitize_prefix(name):
    """Sanitize a string for use as an S3 key component."""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def build_client_prefix(client_name, client_address):
    """Build the S3 key prefix for a client's files.

    Returns a string like 'property-files/john-doe-123-main-st'.
    """
    folder_name = f"{client_name} - {client_address}"
    return f"property-files/{sanitize_prefix(folder_name)}"


def upload_file(file_content, key, mime_type='application/octet-stream'):
    """Upload a file to R2.

    Args:
        file_content: bytes or file-like object
        key: full S3 object key
        mime_type: MIME type

    Returns:
        The object key
    """
    client = get_r2_client()
    if isinstance(file_content, (bytes, bytearray)):
        body = file_content
    else:
        body = file_content.read()
    client.put_object(
        Bucket=_bucket(),
        Key=key,
        Body=body,
        ContentType=mime_type,
    )
    return key


def download_file(key):
    """Download a file from R2.

    Returns:
        File content as bytes
    """
    client = get_r2_client()
    response = client.get_object(Bucket=_bucket(), Key=key)
    return response['Body'].read()


def delete_file(key):
    """Delete a file from R2.

    Returns:
        True on success, False on error
    """
    try:
        client = get_r2_client()
        client.delete_object(Bucket=_bucket(), Key=key)
        return True
    except Exception as e:
        print(f"Error deleting file from R2: {e}")
        return False


def generate_presigned_url(key, expiration=3600):
    """Generate a presigned GET URL for a file in R2.

    Args:
        key: S3 object key
        expiration: seconds until the URL expires (default 1 hour)

    Returns:
        Presigned URL string
    """
    client = get_r2_client()
    return client.generate_presigned_url(
        'get_object',
        Params={'Bucket': _bucket(), 'Key': key},
        ExpiresIn=expiration,
    )
