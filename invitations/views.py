from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Invitation
from .serializers import InvitationSerializer, InvitationCreateSerializer
from .tasks import send_invitation_email, send_reminder_email

User = get_user_model()

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
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create invitation with optimized flow"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Check if user already exists
        email = serializer.validated_data['email']
        existing_user = User.objects.filter(email=email).first()
        
        if existing_user:
            # For existing users, we still create invitation but with different flow
            invitation = serializer.save()
            
            # Send email for existing user (they can accept/decline)
            send_invitation_email.delay(
                str(invitation.id),
                invitation.invited_by.full_name or invitation.invited_by.email,
                is_existing_user=True
            )
            
            return Response({
                'message': 'Invitation sent to existing user',
                'user_exists': True,
                'invitation_id': str(invitation.id)
            }, status=status.HTTP_201_CREATED)
        else:
            # For new users, standard flow
            invitation = serializer.save()
            
            # Send email for new user registration
            send_invitation_email.delay(
                str(invitation.id),
                invitation.invited_by.full_name or invitation.invited_by.email,
                is_existing_user=False
            )
            
            return Response({
                'message': 'Invitation sent to new user',
                'user_exists': False,
                'invitation_id': str(invitation.id)
            }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'])
    def accept_invitation(self, request):
        """Accept invitation - different flow for existing vs new users"""
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = Invitation.objects.get_valid_invitation(token)
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
            
            # Update user type if different (e.g., user becoming owner)
            if request.user.user_type != invitation.invitation_type:
                request.user.user_type = invitation.invitation_type
                request.user.save()
                
                # If becoming owner, create trust levels
                if invitation.invitation_type == 'owner':
                    from accounts.tasks import create_owner_defaults
                    create_owner_defaults.delay(str(request.user.id))
            
            # Mark invitation as accepted
            invitation.status = 'accepted'
            invitation.accepted_by = request.user
            invitation.accepted_at = timezone.now()
            invitation.save()
            
            return Response({
                'message': 'Invitation accepted successfully',
                'user_type': request.user.user_type,
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
                    # Create user
                    user = User.objects.create_user(
                        email=invitation.email,
                        username=invitation.email,
                        full_name=user_data['full_name'],
                        phone=user_data.get('phone', ''),
                        user_type=invitation.invitation_type,
                        status='active',
                        email_verified=True,
                        password=user_data['password']
                    )
                    
                    # Update invitation
                    invitation.status = 'accepted'
                    invitation.accepted_by = user
                    invitation.accepted_at = timezone.now()
                    invitation.save()
                    
                    # Clear related caches
                    cache.delete(f'invitation_token_{token}')
                    cache.delete(f'user_pending_invitations_{invitation.email}')
                    
                    # For owners, trigger setup
                    if user.user_type == 'owner':
                        from accounts.tasks import create_owner_defaults
                        create_owner_defaults.delay(str(user.id))
                    
                    return Response({
                        'message': 'Account created successfully',
                        'user': {
                            'id': str(user.id),
                            'email': user.email,
                            'full_name': user.full_name,
                            'user_type': user.user_type
                        },
                        'requires_login': True
                    }, status=status.HTTP_201_CREATED)
                    
            except Exception as e:
                return Response(
                    {'error': f'Failed to create account: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
    
    @action(detail=False, methods=['post'])
    def decline_invitation(self, request):
        """Decline invitation (for existing users)"""
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = Invitation.objects.get_valid_invitation(token)
        if not invitation:
            return Response(
                {'error': 'Invalid or expired invitation token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark invitation as declined
        invitation.status = 'declined'
        invitation.save()
        
        # Clear cache
        cache.delete(f'invitation_token_{token}')
        
        return Response({
            'message': 'Invitation declined successfully'
        })
