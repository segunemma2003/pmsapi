from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import uuid
import os
from PIL import Image
import io

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_file(request):
    """Handle file uploads"""
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    file = request.FILES['file']
    folder = request.data.get('folder', 'general')
    
    # Validate file size (max 10MB)
    if file.size > 10 * 1024 * 1024:
        return Response(
            {'error': 'File size exceeds 10MB limit'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate file type
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx']
    file_extension = os.path.splitext(file.name)[1].lower()
    
    if file_extension not in allowed_extensions:
        return Response(
            {'error': f'File type {file_extension} not allowed'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = f"{folder}/{unique_filename}"
        
        # For images, resize if too large
        if file_extension in ['.jpg', '.jpeg', '.png']:
            # Open image and resize if needed
            image = Image.open(file)
            
            # Max dimensions
            max_width, max_height = 1920, 1080
            
            if image.width > max_width or image.height > max_height:
                # Calculate new dimensions maintaining aspect ratio
                ratio = min(max_width / image.width, max_height / image.height)
                new_width = int(image.width * ratio)
                new_height = int(image.height * ratio)
                
                # Resize image
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save resized image to bytes
                img_byte_arr = io.BytesIO()
                format = 'JPEG' if file_extension in ['.jpg', '.jpeg'] else 'PNG'
                image.save(img_byte_arr, format=format, quality=85, optimize=True)
                img_byte_arr.seek(0)
                
                # Create new file object
                file = ContentFile(img_byte_arr.read(), name=unique_filename)
        
        # Save file
        saved_path = default_storage.save(file_path, file)
        
        # Get file URL
        if hasattr(settings, 'AWS_STORAGE_BUCKET_NAME'):
            # S3 storage
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{saved_path}"
        else:
            # Local storage
            file_url = f"{settings.MEDIA_URL}{saved_path}"
        
        return Response({
            'success': True,
            'file_url': file_url,
            'file_path': saved_path,
            'original_name': file.name,
            'size': file.size,
            'content_type': file.content_type
        })
        
    except Exception as e:
        return Response(
            {'error': f'Upload failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_file(request):
    """Delete uploaded file"""
    file_path = request.data.get('file_path')
    
    if not file_path:
        return Response(
            {'error': 'File path required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        if default_storage.exists(file_path):
            default_storage.delete(file_path)
            return Response({'success': True, 'message': 'File deleted'})
        else:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    except Exception as e:
        return Response(
            {'error': f'Delete failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )