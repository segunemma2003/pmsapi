from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import TrustLevelDefinition, OwnerTrustedNetwork, TrustedNetworkInvitation
from .serializers import (
    TrustLevelDefinitionSerializer, OwnerTrustedNetworkSerializer,
    TrustedNetworkInvitationSerializer, TrustedNetworkInvitationCreateSerializer
)

import uuid

User = get_user_model()

class TrustedNetworkInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = TrustedNetworkInvitationSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.user_type == 'owner':
                return TrustedNetworkInvitation.objects.filter(
                    owner=user
                ).order_by('-created_at')
        return TrustedNetworkInvitation.objects.none()
        
    
    def get_permissions(self):
        """Override permissions per action"""
        if self.action == 'create':
            # Only create requires authentication
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['list', 'retrieve', 'update', 'partial_update', 'destroy']:
            # CRUD operations require authentication
            permission_classes = [permissions.IsAuthenticated]
        else:
            # accept_invitation, decline_invitation, validate_token allow any
            permission_classes = [permissions.AllowAny]
        
        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TrustedNetworkInvitationCreateSerializer
        return TrustedNetworkInvitationSerializer
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create trusted network invitation"""
        if request.user.user_type != 'owner':
            return Response(
                {'error': 'Only owners can create network invitations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get trust level definition for discount
        try:
            trust_level_def = TrustLevelDefinition.objects.get(
                owner=request.user,
                level=serializer.validated_data['trust_level']
            )
        except TrustLevelDefinition.DoesNotExist:
            return Response(
                {'error': 'Invalid trust level'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists
        email = serializer.validated_data['email']
        existing_user = User.objects.filter(email=email).first()
        
        # Create invitation
        invitation = serializer.save(
            owner=request.user,
            discount_percentage=trust_level_def.default_discount_percentage,
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )
        
        # Send email asynchronously
        from .tasks import send_trusted_network_invitation_email
        send_trusted_network_invitation_email.delay(
            str(invitation.id), 
            user_exists=bool(existing_user)
        )
        
        return Response({
            'message': f'Network invitation sent to {"existing" if existing_user else "new"} user',
            'user_exists': bool(existing_user),
            'invitation': TrustedNetworkInvitationSerializer(invitation).data
        }, status=status.HTTP_201_CREATED)
        
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def validate_token(self, request):
        """Validate network invitation token"""
        token = request.data.get('token') or request.query_params.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # This will raise ValueError if the UUID is malformed
            uuid.UUID(token)
        except ValueError:
            return Response(
                {'error': 'Invalid token format'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        invitation = TrustedNetworkInvitation.objects.get_valid_invitation(token)
        if not invitation:
            return Response({
                'valid': False,
                'error': 'Invalid or expired invitation token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        existing_user = User.objects.filter(email=invitation.email).first()
        
        already_in_network = False
        if existing_user:
            already_in_network = OwnerTrustedNetwork.objects.filter(
                owner=invitation.owner,
                trusted_user=existing_user,
                status='active'
            ).exists()
        
        response_data = {
            'valid': True,
            'invitation': {
                'email': invitation.email,
                'invitee_name': invitation.invitee_name,
                'owner_name': invitation.owner.full_name,
                'trust_level': invitation.trust_level,
                'discount_percentage': float(invitation.discount_percentage),
                'expires_at': invitation.expires_at.isoformat(),
                'personal_message': invitation.personal_message
            },
            'user_status': {
                'exists': bool(existing_user),
                'current_type': existing_user.user_type if existing_user else None,
                'needs_login': bool(existing_user),
                'needs_registration': not bool(existing_user),
                'already_in_network': already_in_network
            }
        }
        return Response(response_data)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def accept_invitation(self, request):
        """Accept trusted network invitation - matches invitation flow"""
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = TrustedNetworkInvitation.objects.get_valid_invitation(token)
        if not invitation:
            return Response(
                {'error': 'Invalid or expired invitation token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists
        existing_user = User.objects.filter(email=invitation.email).first()
        
        if existing_user:
            # Existing user accepting invitation
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Please login to accept this invitation'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            if request.user.email != invitation.email:
                return Response(
                    {'error': 'Invitation email does not match your account'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            with transaction.atomic():
                # Add to trusted network
                network, created = OwnerTrustedNetwork.objects.get_or_create(
                    owner=invitation.owner,
                    trusted_user=request.user,
                    defaults={
                        'trust_level': invitation.trust_level,
                        'discount_percentage': invitation.discount_percentage,
                        'invitation_id': invitation.id,
                        'status': 'active'
                    }
                )
                
                if not created:
                    # Update existing network
                    network.trust_level = invitation.trust_level
                    network.discount_percentage = invitation.discount_percentage
                    network.status = 'active'
                    network.save()
                
                # Mark invitation as accepted
                invitation.status = 'accepted'
                invitation.accepted_at = timezone.now()
                invitation.save()
            
            return Response({
                'message': f'Successfully joined {invitation.owner.full_name}\'s trusted network',
                'network_details': {
                    'owner_name': invitation.owner.full_name,
                    'trust_level': invitation.trust_level,
                    'discount_percentage': float(invitation.discount_percentage)
                },
                'requires_login': False
            })
        
        else:
            # New user - need registration data
            user_data = request.data.get('user_data', {})
            
            if not user_data:
                return Response(
                    {'error': 'User registration data required for new users'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            required_fields = ['password', 'full_name']
            missing_fields = [field for field in required_fields if not user_data.get(field)]
            
            if missing_fields:
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                with transaction.atomic():
                    # Create user (default as 'user' type)
                    user = User.objects.create_user(
                        email=invitation.email,
                        username=invitation.email,
                        full_name=user_data['full_name'],
                        phone=user_data.get('phone', ''),
                        user_type='user',  # Trust level invitations create regular users
                        status='active',
                        email_verified=True,
                        password=user_data['password']
                    )
                    
                    # Add to trusted network
                    network = OwnerTrustedNetwork.objects.create(
                        owner=invitation.owner,
                        trusted_user=user,
                        trust_level=invitation.trust_level,
                        discount_percentage=invitation.discount_percentage,
                        invitation_id=invitation.id,
                        status='active'
                    )
                    
                    # Update invitation
                    invitation.status = 'accepted'
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                    
                    # Clear related caches
                    cache.delete(f'network_invitation_token_{token}')
                    
                    return Response({
                        'message': 'Account created and added to trusted network successfully',
                        'user': {
                            'id': str(user.id),
                            'email': user.email,
                            'full_name': user.full_name,
                            'user_type': user.user_type
                        },
                        'network_details': {
                            'owner_name': invitation.owner.full_name,
                            'trust_level': invitation.trust_level,
                            'discount_percentage': float(invitation.discount_percentage)
                        },
                        'requires_login': True
                    }, status=status.HTTP_201_CREATED)
                    
            except Exception as e:
                return Response(
                    {'error': f'Failed to create account: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def pending_for_user(self, request):
        """Get pending trust network invitations for the current user"""
        user_email = request.user.email
        
        # Find all pending trust network invitations for this user's email
        pending_invitations = TrustedNetworkInvitation.objects.filter(
            email=user_email,
            status='pending',
            expires_at__gt=timezone.now()
        ).select_related('owner').order_by('-created_at')
        
        # Serialize the invitations
        serializer = self.get_serializer(pending_invitations, many=True)
        
        # Enhance with trust level names
        enhanced_invitations = []
        for invitation_data in serializer.data:
            enhanced_data = dict(invitation_data)
            
            # Get trust level name
            try:
                trust_def = TrustLevelDefinition.objects.get(
                    owner_id=invitation_data['owner'],
                    level=invitation_data['trust_level']
                )
                enhanced_data['trust_level_name'] = trust_def.name
                enhanced_data['trust_level_color'] = trust_def.color
            except TrustLevelDefinition.DoesNotExist:
                enhanced_data['trust_level_name'] = f"Level {invitation_data['trust_level']}"
                enhanced_data['trust_level_color'] = '#3B82F6'
            
            enhanced_invitations.append(enhanced_data)
        
        return Response({
            'count': pending_invitations.count(),
            'invitations': enhanced_invitations
        })
        
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def decline_invitation(self, request):
        """Decline trusted network invitation"""
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = TrustedNetworkInvitation.objects.get_valid_invitation(token)
        if not invitation:
            return Response(
                {'error': 'Invalid or expired invitation token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark invitation as declined
        invitation.status = 'declined'
        invitation.save()
        
        # Clear cache
        cache.delete(f'network_invitation_token_{token}')
        
        return Response({
            'message': 'Network invitation declined successfully'
        })
    
    # Keep the old method for backward compatibility
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def respond_to_invitation(self, request):
        """Legacy method - redirect to new methods"""
        action = request.data.get('action')
        
        if action == 'accept':
            return self.accept_invitation(request)
        elif action == 'decline':
            return self.decline_invitation(request)
        else:
            return Response(
                {'error': 'Valid action required (accept/decline)'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
class TrustLevelDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = TrustLevelDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return TrustLevelDefinition.objects.filter(owner=user)
        return TrustLevelDefinition.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class OwnerTrustedNetworkViewSet(viewsets.ModelViewSet):
    serializer_class = OwnerTrustedNetworkSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return OwnerTrustedNetwork.objects.filter(owner=user)
        elif user.user_type == 'user':
            return OwnerTrustedNetwork.objects.filter(trusted_user=user)
        return OwnerTrustedNetwork.objects.none()
    
    @action(detail=True, methods=['patch'])
    def update_trust_level(self, request, pk=None):
        """Update trust level for a network member"""
        network = self.get_object()
        
        if network.owner != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        new_level = request.data.get('trust_level')
        if not new_level:
            return Response(
                {'error': 'Trust level required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate trust level exists
        try:
            trust_level_def = TrustLevelDefinition.objects.get(
                owner=request.user,
                level=new_level
            )
        except TrustLevelDefinition.DoesNotExist:
            return Response(
                {'error': 'Invalid trust level'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        network.trust_level = new_level
        network.discount_percentage = trust_level_def.default_discount_percentage
        network.save()
        
        return Response({
            'message': 'Trust level updated successfully',
            'trust_level': new_level,
            'discount_percentage': float(network.discount_percentage)
        })
    
    @action(detail=True, methods=['delete'])
    def remove_from_network(self, request, pk=None):
        """Remove user from trusted network"""
        network = self.get_object()
        
        if network.owner != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        network.delete()
        
        return Response({
            'message': 'User removed from network successfully'
        })