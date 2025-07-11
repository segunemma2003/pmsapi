from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .serializers import RoleSwitchSerializer, UserProfileUpdateSerializer, UserSerializer, UserRegistrationSerializer
from .tasks import create_owner_defaults
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q
from django.conf import settings
from django.utils.crypto import get_random_string
import json

User = get_user_model()

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        effective_role = user.get_effective_role()
        
        if user.user_type == 'admin':
            return User.objects.all().order_by('-date_joined')
        elif effective_role == 'owner':
            # Owners can see users in their trusted network
            from trust_levels.models import OwnerTrustedNetwork
            trusted_user_ids = OwnerTrustedNetwork.objects.filter(
                owner=user, status='active'
            ).values_list('trusted_user_id', flat=True)
            return User.objects.filter(
                Q(id__in=trusted_user_ids) | Q(id=user.id)
            )
        else:
            # Users can only see themselves
            return User.objects.filter(id=user.id)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        """Register new user with mandatory invitation token"""
        serializer = UserRegistrationSerializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            
            return Response({
                'message': 'Registration successful. Please check your email for confirmation.',
                'user_id': str(user.id),
                'user_type': user.user_type,
                'current_role': user.current_role
            }, status=status.HTTP_201_CREATED)
            
        except serializers.ValidationError as e:
            # Return specific validation errors
            return Response({
                'error': 'Registration failed',
                'details': e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            # Handle unexpected errors
            return Response({
                'error': 'Registration failed due to server error',
                'message': 'Please try again or contact support'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Update current user profile including avatar and about me"""
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Return full user data
        return Response(
            UserSerializer(request.user).data
        )
        
        
    @action(detail=False, methods=['post'])
    def switch_role(self, request):
        """Switch between owner and user roles"""
        serializer = RoleSwitchSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        
        new_role = serializer.validated_data['new_role']
        
        if request.user.switch_role(new_role):
            # Clear relevant caches
            cache.delete(f'user_profile_{request.user.id}')
            cache.delete(f'user_accessible_properties_{request.user.id}')
            
            return Response({
                'message': f'Successfully switched to {new_role} role',
                'current_role': request.user.current_role,
                'user_type': request.user.user_type
            })
        else:
            return Response(
                {'error': 'Failed to switch role'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search users - filtered by effective role"""
        query = request.GET.get('search', '')
        user_type = request.GET.get('user_type')
        
        # if not query:
        #     return Response([])
        
        effective_role = request.user.get_effective_role()
        
        # Only allow searching if user is admin or acting as owner
        if request.user.user_type != 'admin' and effective_role != 'owner':
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        queryset = User.objects.filter(status='active')
        
        if query:
            # Text search
            queryset = queryset.filter(
                Q(full_name__icontains=query) |
                Q(email__icontains=query)
            )
        
        # Filter by user type
        if user_type:
            queryset = queryset.filter(user_type=user_type)
        
        # If acting as owner, only show users they could invite
        if effective_role == 'owner' and request.user.user_type != 'admin':
            # Exclude users already in their network
            from trust_levels.models import OwnerTrustedNetwork
            existing_network = OwnerTrustedNetwork.objects.filter(
                owner=request.user,
                status='active'
            ).values_list('trusted_user_id', flat=True)
            queryset = queryset.exclude(id__in=existing_network)
        
        # Limit results
        queryset = queryset[:20]
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    

    @action(detail=False, methods=['get'])
    def trust_connections(self, request):
        """Get detailed trust network connections"""
        connections = request.user.get_trust_connections()
        
        # Enhance with owner details
        enhanced_connections = []
        for conn in connections:
            enhanced_conn = dict(conn)
            # Get trust level name
            try:
                from trust_levels.models import TrustLevelDefinition
                trust_def = TrustLevelDefinition.objects.get(
                    owner_id=conn['owner__id'],
                    level=conn['trust_level']
                )
                enhanced_conn['trust_level_name'] = trust_def.name
                enhanced_conn['trust_level_color'] = trust_def.color
            except:
                enhanced_conn['trust_level_name'] = f"Level {conn['trust_level']}"
                enhanced_conn['trust_level_color'] = '#3B82F6'
            
            enhanced_connections.append(enhanced_conn)
        
        return Response({
            'count': len(enhanced_connections),
            'connections': enhanced_connections
        })


    @action(detail=False, methods=['get'])
    def available_properties_count(self, request):
        """Get count of properties user has access to"""
        if request.user.get_effective_role() == 'owner':
            # Owners see their own properties count
            from properties.models import Property
            count = Property.objects.filter(
                owner=request.user,
                status='active'
            ).count()
        else:
            # Users see properties from their trust network
            from trust_levels.models import OwnerTrustedNetwork
            from properties.models import Property
            
            trusted_owners = OwnerTrustedNetwork.objects.filter(
                trusted_user=request.user,
                status='active'
            ).values_list('owner_id', flat=True)
            
            count = Property.objects.filter(
                owner__in=trusted_owners,
                status='active',
                is_visible=True
            ).count()
        
        return Response({
            'available_properties': count,
            'current_role': request.user.get_effective_role()
        })
        
        
    @action(detail=False, methods=['post'])
    def upload_avatar(self, request):
        """Handle avatar upload"""
        if 'avatar' not in request.FILES:
            return Response(
                {'error': 'No avatar file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        avatar_file = request.FILES['avatar']
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return Response(
                {'error': 'Invalid file type. Allowed types: JPEG, PNG, GIF, WebP'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate file size (max 5MB)
        if avatar_file.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'File too large. Maximum size is 5MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use the upload service
        from upload.services import UploadService
        upload_service = UploadService()
        
        try:
            # Upload file
            file_url = upload_service.upload_file(
                avatar_file,
                folder=f'avatars/{request.user.id}',
                allowed_types=allowed_types
            )
            
            # Update user avatar URL
            request.user.avatar_url = file_url
            request.user.save()
            
            return Response({
                'message': 'Avatar uploaded successfully',
                'avatar_url': file_url
            })
            
        except Exception as e:
            return Response(
                {'error': f'Failed to upload avatar: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user password"""
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        if not old_password or not new_password:
            return Response(
                {'error': 'Both old and new passwords are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        
        # Check old password
        if not user.check_password(old_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate new password
        try:
            validate_password(new_password, user)
        except serializers.ValidationError as e:
            return Response(
                {'error': e.messages},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        return Response({'message': 'Password changed successfully'})

    @action(detail=False, methods=['post'])
    def reset_password(self, request):
        """Request password reset"""
        email = request.data.get('email')
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email)
            
            # Generate reset token
            reset_token = get_random_string(32)
            
            # Store token in cache (expires in 1 hour)
            cache.set(f'password_reset_{reset_token}', user.id, timeout=3600)
            
            # Send reset email
            reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
            
            send_mail(
                subject='Password Reset - OnlyIfYouKnow',
                message=f'Click here to reset your password: {reset_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False
            )
            
            return Response({'message': 'Password reset email sent'})
            
        except User.DoesNotExist:
            # Don't reveal if email exists
            return Response({'message': 'Password reset email sent'})

    @action(detail=False, methods=['post'])
    def reset_password_confirm(self, request):
        """Confirm password reset"""
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not token or not new_password:
            return Response(
                {'error': 'Token and new password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get user ID from cache
        user_id = cache.get(f'password_reset_{token}')
        if not user_id:
            return Response(
                {'error': 'Invalid or expired reset token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(id=user_id)
            
            # Validate new password
            try:
                validate_password(new_password, user)
            except serializers.ValidationError as e:
                return Response(
                    {'error': e.messages},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Set new password
            user.set_password(new_password)
            user.save()
            
            # Delete reset token
            cache.delete(f'password_reset_{token}')
            
            return Response({'message': 'Password reset successfully'})
            
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid reset token'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def preferences(self, request):
        """Get user preferences"""
        preferences = getattr(request.user, 'metadata', {}).get('preferences', {})
        return Response(preferences)

    @action(detail=False, methods=['patch'])
    def update_preferences(self, request):
        """Update user preferences"""
        user = request.user
        metadata = user.metadata or {}
        metadata['preferences'] = {
            **metadata.get('preferences', {}),
            **request.data
        }
        user.metadata = metadata
        user.save()
        
        return Response(metadata['preferences'])

    @action(detail=False, methods=['delete'])
    def delete_account(self, request):
        """Delete user account"""
        password = request.data.get('password')
        
        if not password:
            return Response(
                {'error': 'Password confirmation required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        
        # Verify password
        if not user.check_password(password):
            return Response(
                {'error': 'Incorrect password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # For owners, check if they have active bookings
        if user.user_type == 'owner':
            from bookings.models import Booking
            active_bookings = Booking.objects.filter(
                property__owner=user,
                status__in=['confirmed', 'pending']
            )
            if active_bookings.exists():
                return Response(
                    {'error': 'Cannot delete account with active bookings'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Soft delete - mark as inactive
        user.status = 'inactive'
        user.email = f"deleted_{user.id}_{user.email}"
        user.save()
        
        return Response({'message': 'Account deleted successfully'})

    @action(detail=False, methods=['get'])
    def export_data(self, request):
        """Export user data (GDPR compliance)"""
        user = request.user
        
        # Collect user data
        data = {
            'user_info': {
                'id': str(user.id),
                'email': user.email,
                'full_name': user.full_name,
                'phone': user.phone,
                'user_type': user.user_type,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
            },
            'properties': [],
            'bookings': [],
            'trust_networks': [],
            'invitations': []
        }
        
        # Add properties if owner
        if user.user_type == 'owner':
            from properties.serializers import PropertySerializer
            properties = user.properties.all()
            data['properties'] = PropertySerializer(properties, many=True).data
            
            # Add trust networks
            from trust_levels.models import OwnerTrustedNetwork
            from trust_levels.serializers import OwnerTrustedNetworkSerializer
            networks = OwnerTrustedNetwork.objects.filter(owner=user)
            data['trust_networks'] = OwnerTrustedNetworkSerializer(networks, many=True).data
        
        # Add bookings
        from bookings.models import Booking
        from bookings.serializers import BookingSerializer
        bookings = Booking.objects.filter(guest=user)
        data['bookings'] = BookingSerializer(bookings, many=True).data
        
        # Add invitations
        from invitations.models import Invitation
        from invitations.serializers import InvitationSerializer
        invitations = Invitation.objects.filter(
            Q(invited_by=user) | Q(accepted_by=user)
        )
        data['invitations'] = InvitationSerializer(invitations, many=True).data
        
        return Response(data)