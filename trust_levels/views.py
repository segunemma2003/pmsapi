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

User = get_user_model()

class TrustedNetworkInvitationViewSet(viewsets.ModelViewSet):
    serializer_class = TrustedNetworkInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return TrustedNetworkInvitation.objects.filter(
                owner=user
            ).order_by('-created_at')
        return TrustedNetworkInvitation.objects.none()
    
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
    
    @action(detail=False, methods=['post'])
    def respond_to_invitation(self, request):
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
                invitation.status = 'expired'
                invitation.save()
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
                # Check if user exists and is authenticated
                if not request.user.is_authenticated:
                    return Response(
                        {'error': 'Authentication required to accept invitation'},
                        status=status.HTTP_401_UNAUTHORIZED
                    )
                
                # Verify email matches
                if request.user.email != invitation.email:
                    return Response(
                        {'error': 'Invitation email does not match your account'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                with transaction.atomic():
                    # Add to network
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
                    
                    invitation.status = 'accepted'
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                
                return Response({
                    'success': True,
                    'action': 'accepted',
                    'message': f'Successfully joined {invitation.owner.full_name}\'s trusted network',
                    'network_details': {
                        'owner_name': invitation.owner.full_name,
                        'trust_level': invitation.trust_level,
                        'discount_percentage': float(invitation.discount_percentage)
                    }
                })
                    
        except TrustedNetworkInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired invitation'}, 
                status=status.HTTP_400_BAD_REQUEST
            )