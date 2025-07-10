import os
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

class UploadService:
    """Service for handling file uploads with optional S3 support"""
    
    def __init__(self):
        self.use_s3 = getattr(settings, 'USE_S3', False)
        if self.use_s3:
            try:
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
            except ImportError:
                print("Warning: boto3 not installed. Falling back to local storage.")
                self.use_s3 = False
    
    def upload_file(self, file, folder='', allowed_types=None):
        """
        Upload file to storage (S3 or local)
        
        Args:
            file: Django UploadedFile object
            folder: Folder path to store file
            allowed_types: List of allowed MIME types
            
        Returns:
            str: URL of uploaded file
        """
        # Validate file type
        if allowed_types and file.content_type not in allowed_types:
            raise ValueError(f"File type {file.content_type} not allowed")
        
        # Generate unique filename
        ext = os.path.splitext(file.name)[1]
        filename = f"{uuid.uuid4()}{ext}"
        
        if folder:
            filepath = f"{folder}/{filename}"
        else:
            filepath = filename
        
        if self.use_s3:
            return self._upload_to_s3(file, filepath)
        else:
            return self._upload_to_local(file, filepath)
    
    def _upload_to_s3(self, file, filepath):
        """Upload file to S3"""
        try:
            # Upload to S3
            self.s3_client.upload_fileobj(
                file,
                self.bucket_name,
                filepath,
                ExtraArgs={
                    'ContentType': file.content_type,
                    'ACL': 'public-read'
                }
            )
            
            # Return S3 URL
            return f"https://{self.bucket_name}.s3.amazonaws.com/{filepath}"
            
        except Exception as e:
            raise Exception(f"Failed to upload to S3: {str(e)}")
    
    def _upload_to_local(self, file, filepath):
        """Upload file to local storage"""
        # Save file
        path = default_storage.save(f"uploads/{filepath}", ContentFile(file.read()))
        
        # Return full URL
        return f"{settings.MEDIA_URL}{path}"
    
    def delete_file(self, file_url):
        """Delete file from storage"""
        if self.use_s3:
            return self._delete_from_s3(file_url)
        else:
            return self._delete_from_local(file_url)
    
    def _delete_from_s3(self, file_url):
        """Delete file from S3"""
        try:
            # Extract key from URL
            key = file_url.replace(f"https://{self.bucket_name}.s3.amazonaws.com/", "")
            
            # Delete from S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
            
        except Exception:
            return False
    
    def _delete_from_local(self, file_url):
        """Delete file from local storage"""
        try:
            # Extract path from URL
            path = file_url.replace(settings.MEDIA_URL, "")
            
            # Delete file
            default_storage.delete(path)
            return True
            
        except:
            return False

# Alternative simple implementation if you don't need S3
class SimpleUploadService:
    """Simplified upload service for local storage only"""
    
    def upload_file(self, file, folder='', allowed_types=None):
        """Upload file to local media storage"""
        # Validate file type
        if allowed_types and file.content_type not in allowed_types:
            raise ValueError(f"File type {file.content_type} not allowed")
        
        # Generate unique filename
        ext = os.path.splitext(file.name)[1]
        filename = f"{uuid.uuid4()}{ext}"
        
        # Create full path
        if folder:
            upload_path = f"uploads/{folder}/{filename}"
        else:
            upload_path = f"uploads/{filename}"
        
        # Save file
        path = default_storage.save(upload_path, ContentFile(file.read()))
        
        # Return full URL
        return f"{settings.MEDIA_URL}{path}"
    
    def delete_file(self, file_url):
        """Delete file from local storage"""
        try:
            # Extract path from URL
            path = file_url.replace(settings.MEDIA_URL, "")
            default_storage.delete(path)
            return True
        except:
            return False