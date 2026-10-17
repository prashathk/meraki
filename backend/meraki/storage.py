"""Private blob storage abstraction; no public file serving route."""
import os
from pathlib import Path
def put(key,content,content_type='application/octet-stream'):
    bucket=os.getenv('STORAGE_BUCKET')
    if bucket:
        from google.cloud import storage
        blob=storage.Client().bucket(bucket).blob(key);blob.upload_from_string(content,content_type=content_type)
        return 'gs://'+bucket+'/'+key
    root=Path(os.getenv('LOCAL_STORAGE','data/objects')).resolve();dest=(root/key).resolve()
    if not dest.is_relative_to(root):raise ValueError('Invalid storage key')
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content);return 'local:'+key
def get(uri):
    if uri.startswith('gs://'):
        from google.cloud import storage
        bucket,key=uri[5:].split('/',1);return storage.Client().bucket(bucket).blob(key).download_as_bytes()
    root=Path(os.getenv('LOCAL_STORAGE','data/objects')).resolve();dest=(root/uri.removeprefix('local:')).resolve()
    if not dest.is_relative_to(root):raise ValueError('Invalid storage key')
    return dest.read_bytes()
