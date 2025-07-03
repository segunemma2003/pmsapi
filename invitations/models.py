from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
import uuid

User = get_user_model()

class InvitationManager(models.Manager):
    def get_valid_invitation(self, token):
        """Get valid, non-expired invitation"""
        cache_key = f'invitation_token_{token}'
        invitation = cache.get(cache_key)
        
        if invitation is None:
            try:
                invitation = self.select_related('invited_by').get(
                    invitation_token=token,
                    status='pending',
                    expires_at__gt=timezone.now()
                )
                cache.set(cache_key, invitation, timeout=300)
            except self.model.DoesNotExist:
                return None
        
        return invitation

class Invitation(models.Model):
    INVITATION_TYPES = (
        ('admin', 'Admin'),
        ('owner', 'Owner'),
        ('user', 'User'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    invitee_name = models.CharField(max_length=255, blank=True)
    invitation_type = models.CharField(max_length=10, choices=INVITATION_TYPES, default='user')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    personal_message = models.TextField(blank=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    accepted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='accepted_invitations'
    )
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Tracking fields
    reminder_count = models.PositiveIntegerField(default=0)
    last_reminder_sent = models.DateTimeField(null=True, blank=True)
    
    objects = InvitationManager()
    
    class Meta:
        db_table = 'invitations'
        indexes = [
            models.Index(fields=['email', 'status']),
            models.Index(fields=['invited_by', 'status']),
            models.Index(fields=['invitation_type', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['email', 'invitation_type'],
                condition=models.Q(status='pending'),
                name='unique_pending_invitation_per_email_type'
            )
        ]
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        
        # Clear cache when invitation is updated
        if self.pk:
            cache.delete(f'invitation_token_{self.invitation_token}')
            cache.delete(f'user_pending_invitations_{self.email}')
        
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Check if invitation is still valid"""
        return (
            self.status == 'pending' and 
            self.expires_at > timezone.now()
        )
    
    def can_send_reminder(self):
        """Check if reminder can be sent (max 3 reminders, 24h apart)"""
        if self.reminder_count >= 3:
            return False
        
        if self.last_reminder_sent:
            time_since_last = timezone.now() - self.last_reminder_sent
            return time_since_last >= timedelta(hours=24)
        
        return True
    
class OnboardingToken(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('used', 'Used'),
        ('expired', 'Expired'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invitation = models.ForeignKey(Invitation, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField(db_index=True)
    user_type = models.CharField(max_length=10, choices=Invitation.INVITATION_TYPES, default='user')
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'onboarding_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email']),
            models.Index(fields=['expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)