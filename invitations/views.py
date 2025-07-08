from trust_levels.models import TrustedNetworkInvitation
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Invitation
from .serializers import InvitationSerializer, InvitationCreateSerializer
from .tasks import send_invitation_email

User = get_user_model()

class InvitationViewSet(viewsets.ModelViewSet):
    serializer_class = InvitationSerializer
    permission_classes = [permissions.AllowAny]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            if user.user_type == 'admin':
                return Invitation.objects.select_related(
                    'invited_by', 'accepted_by'
                ).all().order_by('-created_at')
            else:
                return Invitation.objects.select_related(
                    'invited_by', 'accepted_by'
                ).filter(invited_by=user).order_by('-created_at')
        else:
            # Return empty queryset for unauthenticated users
            return Invitation.objects.none()
    
    def get_serializer_class(self):
        if self.action == 'create':
            return InvitationCreateSerializer
        return InvitationSerializer
    
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
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
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
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
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
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def validate_token(self, request):
        """Validate invitation token"""
        token = request.data.get('token')
        
        if not token:
            return Response(
                {'error': 'Token is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        invitation = Invitation.objects.get_valid_invitation(token)
        if not invitation:
            return Response({
                'valid': False,
                'error': 'Invalid or expired invitation token'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'valid': True,
            'invitation': {
                'email': invitation.email,
                'invitee_name': invitation.invitee_name,
                'invitation_type': invitation.invitation_type,
                'inviter_name': invitation.invited_by.full_name,
                'expires_at': invitation.expires_at.isoformat(),
                'personal_message': invitation.personal_message
            }
        })
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def check_task_status(self, request):
        """Check the status of a Celery task - NO AUTHENTICATION REQUIRED"""
        task_id = request.GET.get('task_id')
        
        if not task_id:
            return Response({'error': 'task_id parameter required'}, status=400)
        
        try:
            from celery.result import AsyncResult
            
            # Get task result
            result = AsyncResult(task_id)
            
            response_data = {
                'task_id': task_id,
                'state': result.state,
                'ready': result.ready(),
                'successful': result.successful() if result.ready() else None,
            }
            
            if result.ready():
                if result.successful():
                    response_data['result'] = result.result
                else:
                    response_data['error'] = str(result.result)
                    response_data['traceback'] = result.traceback
            
            # Also check if any workers are active
            from celery import current_app
            inspect = current_app.control.inspect()
            
            try:
                active_workers = inspect.active()
                response_data['workers_active'] = bool(active_workers)
                response_data['active_workers'] = list(active_workers.keys()) if active_workers else []
            except:
                response_data['workers_active'] = False
                response_data['active_workers'] = []
            
            return Response(response_data)
            
        except Exception as e:
            return Response({
                'error': f'Failed to check task status: {str(e)}',
                'task_id': task_id
            }, status=500)
            
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def resend_invitation(self, request, pk=None):
        """Resend invitation email - REQUIRES AUTHENTICATION"""
        try:
            invitation = self.get_object()
            
            # Check permissions - only the inviter or admin can resend
            if invitation.invited_by != request.user and request.user.user_type != 'admin':
                return Response(
                    {'error': 'Permission denied. Only the inviter or admin can resend invitations.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Check if invitation is still pending
            if invitation.status != 'pending':
                return Response(
                    {'error': f'Cannot resend invitation. Status is "{invitation.status}".'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if invitation has expired
            if not invitation.is_valid():
                return Response(
                    {'error': 'Cannot resend expired invitation. Please create a new invitation.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check reminder limits
            if not invitation.can_send_reminder():
                if invitation.reminder_count >= 3:
                    return Response(
                        {'error': 'Maximum number of reminders (3) already sent for this invitation.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': 'Must wait 24 hours between reminder emails.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Update reminder tracking
            invitation.reminder_count += 1
            invitation.last_reminder_sent = timezone.now()
            invitation.save()
            
            # Check if user already exists to determine email type
            existing_user = User.objects.filter(email=invitation.email).first()
            
            # Queue email task
            print(f"🔄 API: Resending invitation email for {invitation.id} (reminder #{invitation.reminder_count})")
            task = send_invitation_email.delay(
                str(invitation.id),
                invitation.invited_by.full_name or invitation.invited_by.email,
                is_existing_user=bool(existing_user)
            )
            print(f"🔄 API: Resend task queued with ID: {task.id}")
            
            return Response({
                'message': f'Invitation resent successfully (reminder #{invitation.reminder_count})',
                'invitation_id': str(invitation.id),
                'task_id': str(task.id),
                'reminder_count': invitation.reminder_count,
                'can_send_more': invitation.reminder_count < 3,
                'next_reminder_available_at': (invitation.last_reminder_sent + timezone.timedelta(hours=24)).isoformat() if invitation.reminder_count < 3 else None
            }, status=status.HTTP_200_OK)
            
        except Invitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to resend invitation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def resend_by_email(self, request):
        """Resend invitation by email address - REQUIRES AUTHENTICATION"""
        email = request.data.get('email')
        invitation_type = request.data.get('invitation_type', 'user')
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Find the most recent pending invitation for this email
            invitation = Invitation.objects.filter(
                email=email,
                invitation_type=invitation_type,
                status='pending',
                invited_by=request.user
            ).order_by('-created_at').first()
            
            if not invitation and request.user.user_type == 'admin':
                # Admins can resend any invitation
                invitation = Invitation.objects.filter(
                    email=email,
                    invitation_type=invitation_type,
                    status='pending'
                ).order_by('-created_at').first()
            
            if not invitation:
                return Response(
                    {'error': f'No pending {invitation_type} invitation found for {email}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Use the detail resend logic
            return self.resend_invitation(request, pk=invitation.pk)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to find invitation: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def celery_status(self, request):
        """Check Celery worker status - NO AUTHENTICATION REQUIRED (for monitoring)"""
        try:
            from celery import current_app
            inspect = current_app.control.inspect()
            
            # Get worker stats
            stats = inspect.stats()
            active = inspect.active()
            
            if not stats:
                return Response({
                    'status': 'error',
                    'message': 'No active Celery workers found'
                }, status=503)
            
            return Response({
                'status': 'healthy',
                'workers': list(stats.keys()) if stats else [],
                'active_tasks': len(active.get(list(stats.keys())[0], [])) if active and stats else 0,
                'worker_count': len(stats) if stats else 0
            })
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=503)

    # Add this method to trust_levels/views.py TrustedNetworkInvitationViewSet

    