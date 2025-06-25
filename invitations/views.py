from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.core.cache import cache
from .models import Invitation, OnboardingToken
from .serializers import (
    InvitationSerializer, InvitationCreateSerializer,
    TrustedNetworkInvitationSerializer, OnboardingTokenSerializer
)
from .tasks import send_invitation_email, send_trusted_network_invitation_email
from trust_levels.models import TrustedNetworkInvitation

class InvitationViewSet(viewsets.ModelViewSet):
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'admin':
            return Invitation.objects.select_related(
                'invited_by', 'accepted_by'
            ).all().order_by('-created_at')
        else:
            return Invitation.objects.select_related(
                'invited_by', 'accepted_by'
            ).filter(invited_by=user).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InvitationCreateSerializer
        return InvitationSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Create invitation
        invitation = serializer.save()
        
        # Create onboarding token
        token = OnboardingToken.objects.create(
            email=invitation.email,
            user_type=invitation.invitation_type,
            invitation=invitation,
            expires_at=invitation.expires_at,
            metadata={
                'invited_by': str(invitation.invited_by.id),
                'invitee_name': invitation.invitee_name,
            }
        )
        
        # Update invitation with token
        invitation.invitation_token = token.token
        invitation.save()
        
        # Send email asynchronously
        send_invitation_email.delay(
            str(invitation.id),
            invitation.invited_by.full_name or invitation.invited_by.email
        )
        
        return Response(
            InvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def validate_token(self, request):
        """Validate onboarding token"""
        token = request.data.get('token')
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            token_obj = OnboardingToken.objects.select_related('invitation').get(
                token=token
            )
            
            # Check if token is valid
            now = timezone.now()
            is_valid = token_obj.expires_at > now and token_obj.used_at is None
            
            return Response({
                'is_valid': is_valid,
                'email': token_obj.email,
                'user_type': token_obj.user_type,
                'invitation_id': str(token_obj.invitation.id) if token_obj.invitation else '',
                'expires_at': token_obj.expires_at,
                'metadata': token_obj.metadata
            })
        except OnboardingToken.DoesNotExist:
            return Response({
                'is_valid': False,
                'email': '',
                'user_type': 'user',
                'invitation_id': ''
            })
    
    @action(detail=False, methods=['post'])
    def respond_to_invitation(self, request):
        """Accept or reject invitation"""
        token = request.data.get('token')
        action = request.data.get('action')  # 'accept' or 'reject'
        
        if not token or action not in ['accept', 'reject']:
            return Response(
                {'error': 'Valid token and action required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            token_obj = OnboardingToken.objects.select_related('invitation').get(
                token=token
            )
            
            # Check if token is valid
            now = timezone.now()
            if token_obj.expires_at <= now or token_obj.used_at:
                return Response(
                    {'error': 'Token has expired or already been used'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if action == 'reject':
                # Mark invitation as declined
                if token_obj.invitation:
                    token_obj.invitation.status = 'declined'
                    token_obj.invitation.save()
                
                # Mark token as used
                token_obj.used_at = now
                token_obj.save()
                
                return Response({
                    'success': True,
                    'action': 'rejected',
                    'message': 'Invitation declined successfully'
                })
            
            elif action == 'accept':
                return Response({
                    'success': True,
                    'action': 'accepted',
                    'token_info': {
                        'user_type': token_obj.user_type,
                        'email': token_obj.email,
                        'invitation_id': str(token_obj.invitation.id) if token_obj.invitation else '',
                        'token': token
                    },
                    'message': 'Invitation accepted. Please complete registration.'
                })
                
        except OnboardingToken.DoesNotExist:
            return Response(
                {'error': 'Invalid token'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

class TrustedNetworkInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = TrustedNetworkInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return TrustedNetworkInvitation.objects.select_related(
                'owner'
            ).filter(owner=user).order_by('-created_at')
        return TrustedNetworkInvitation.objects.none()
    
    def create(self, request, *args, **kwargs):
        # Only owners can create trusted network invitations
        if request.user.user_type != 'owner':
            return Response(
                {'error': 'Only owners can create network invitations'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get trust level definition for discount
        from trust_levels.models import TrustLevelDefinition
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
        
        # Create invitation
        invitation = serializer.save(
            owner=request.user,
            discount_percentage=trust_level_def.default_discount_percentage,
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )
        
        # Send email asynchronously
        send_trusted_network_invitation_email.delay(str(invitation.id))
        
        return Response(
            TrustedNetworkInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['post'])
    def respond_to_network_invitation(self, request):
        """Respond to trusted network invitation"""
        token = request.data.get('token')
        action = request.data.get('action')  # 'accept' or 'decline'
        
        if not token or action not in ['accept', 'decline']:
            return Response(
                {'error': 'Valid token and action required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            invitation = TrustedNetworkInvitation.objects.select_related('owner').get(
                invitation_token=token,
                status='pending'
            )
            
            # Check if invitation is expired
            if invitation.expires_at <= timezone.now():
                return Response(
                    {'error': 'Invitation has expired'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if action == 'decline':
                invitation.status = 'declined'
                invitation.save()
                
                return Response({
                    'success': True,
                    'action': 'declined',
                    'message': 'Network invitation declined'
                })
            
            elif action == 'accept':
                user = request.user
                
                if user.is_authenticated:
                    # User exists - add to network
                    from trust_levels.models import OwnerTrustedNetwork
                    
                    network, created = OwnerTrustedNetwork.objects.get_or_create(
                        owner=invitation.owner,
                        trusted_user=user,
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
                    
                    invitation.status = 'accepted'
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                    
                    # Clear relevant caches
                    cache.delete(f'trust_network_size_{invitation.owner.id}')
                    cache.delete(f'user_accessible_properties_{user.id}')
                    
                    return Response({
                        'success': True,
                        'action': 'accepted',
                        'user_exists': True,
                        'message': 'Added to trusted network successfully'
                    })
                else:
                    # User needs to register first
                    invitation.status = 'accepted'
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                    
                    return Response({
                        'success': True,
                        'action': 'accepted',
                        'user_exists': False,
                        'invitation_data': {
                            'email': invitation.email,
                            'invitee_name': invitation.invitee_name,
                            'trust_level': invitation.trust_level,
                            'owner_name': invitation.owner.full_name,
                            'token': token
                        },
                        'message': 'Please complete registration to join the network'
                    })
                    
        except TrustedNetworkInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired invitation'}, 
                status=status.HTTP_400_BAD_REQUEST
            )