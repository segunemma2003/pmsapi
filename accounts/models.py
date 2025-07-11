import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.cache import cache
from django.utils import timezone

class User(AbstractUser):
    USER_TYPES = (
        ('admin', 'Admin'),
        ('owner', 'Owner'),
        ('user', 'User'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(blank=True)
    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='user')
    
    # New field for role switching
    current_role = models.CharField(max_length=10, choices=USER_TYPES, default='user')
    about_me = models.TextField(blank=True, max_length=1000)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    onboarding_completed = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    last_active_at = models.DateTimeField(null=True, blank=True)
    trust_network_count = models.PositiveIntegerField(default=0)
    beds24_subaccount_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['user_type']),
            models.Index(fields=['current_role']),
            models.Index(fields=['status']),
            models.Index(fields=['beds24_subaccount_id']),
        ]
    
    def save(self, *args, **kwargs):
        # Clear user cache on save
        cache.delete(f'user_profile_{self.id}')
        cache.delete(f'user_trust_connections_{self.id}')
        self.clear_user_caches()
        super().save(*args, **kwargs)
    
    def get_trust_network_size(self):
        """Get cached trust network size for owners"""
        if self.user_type == 'owner':
            cache_key = f'trust_network_size_{self.id}'
            size = cache.get(cache_key)
            if size is None:
                from trust_levels.models import OwnerTrustedNetwork
                size = OwnerTrustedNetwork.objects.filter(
                    owner=self, status='active'
                ).count()
                cache.set(cache_key, size, timeout=300)  # 5 minutes
            return size
        return 0
    
    def get_trust_connections(self):
        """Get all trust network connections for this user"""
        cache_key = f'user_trust_connections_{self.id}'
        connections = cache.get(cache_key)
        
        if connections is None:
            from trust_levels.models import OwnerTrustedNetwork
            connections = list(OwnerTrustedNetwork.objects.filter(
                trusted_user=self,
                status='active'
            ).select_related('owner').values(
                'owner__id',
                'owner__full_name',
                'owner__email',
                'trust_level',
                'discount_percentage',
                'added_at'
            ))
            cache.set(cache_key, connections, timeout=300)  # 5 minutes
        
        return connections
    
    def can_switch_role(self):
        """Check if user can switch between owner and user roles"""
        if self.status != 'active':
            return False
        
        if self.user_type == 'owner':
            # Owner can only switch roles if they are under another owner's network
            return self.is_under_owner_network()
        
        elif self.user_type == 'user':
            # User can only switch roles if they were invited by admin to become owner and accepted
            return self.has_accepted_admin_owner_invitation()
        
        return False
    
    def is_under_owner_network(self):
        """Check if this owner is part of another owner's trust network"""
        if self.user_type != 'owner':
            return False
        
        cache_key = f'user_under_network_{self.id}'
        result = cache.get(cache_key)
        
        if result is None:
            from trust_levels.models import OwnerTrustedNetwork
            # Check if this owner is a trusted user in another owner's network
            result = OwnerTrustedNetwork.objects.filter(
                trusted_user=self,
                status='active',
                owner__user_type='owner'
            ).exists()
            cache.set(cache_key, result, timeout=300)  # 5 minutes
        
        return result


    def has_accepted_admin_owner_invitation(self):
        """Check if user has accepted an admin invitation to become owner"""
        if self.user_type != 'user':
            return False
        
        cache_key = f'user_admin_invitation_{self.id}'
        result = cache.get(cache_key)
        
        if result is None:
            from invitations.models import Invitation
            # Check if user has accepted an owner invitation from an admin
            result = Invitation.objects.filter(
                email=self.email,
                invitation_type='owner',
                status='accepted',
                invited_by__user_type='admin',
                accepted_by=self
            ).exists()
            cache.set(cache_key, result, timeout=300)  # 5 minutes
        
        return result

    def switch_role(self, new_role):
        """Switch current role between owner and user with enhanced validation"""
        if not self.can_switch_role():
            return False
        
        if new_role not in ['owner', 'user']:
            return False
        
        # Enhanced role switching logic
        if self.user_type == 'owner':
            # Owner can switch between owner and user roles if under network
            if new_role in ['owner', 'user'] and self.is_under_owner_network():
                self.current_role = new_role
                self.save()
                # Clear relevant caches
                cache.delete(f'user_effective_role_{self.id}')
                return True
        
        elif self.user_type == 'user':
            # User can become owner if they have accepted admin invitation
            if new_role == 'owner' and self.has_accepted_admin_owner_invitation():
                self.current_role = new_role
                self.save()
                # Clear relevant caches
                cache.delete(f'user_effective_role_{self.id}')
                return True
            # User can always switch back to user role
            elif new_role == 'user':
                self.current_role = new_role
                self.save()
                # Clear relevant caches
                cache.delete(f'user_effective_role_{self.id}')
                return True
        
        return False
    
    def get_effective_role(self):
        """Get the effective role for permissions checking with caching"""
        cache_key = f'user_effective_role_{self.id}'
        effective_role = cache.get(cache_key)
        
        if effective_role is None:
            # If current_role is not set, use user_type
            if not self.current_role:
                effective_role = self.user_type
            else:
                # Ensure current_role doesn't exceed user_type permissions
                if self.user_type == 'user':
                    # Users can be 'user' or 'owner' if they have admin invitation
                    if self.current_role == 'owner' and self.has_accepted_admin_owner_invitation():
                        effective_role = 'owner'
                    else:
                        effective_role = 'user'
                elif self.user_type == 'owner':
                    # Owners can switch between owner and user if under network
                    if self.current_role in ['owner', 'user'] and self.is_under_owner_network():
                        effective_role = self.current_role
                    else:
                        effective_role = 'owner'  # Default to owner if not under network
                elif self.user_type == 'admin':
                    effective_role = 'admin'  # Admins always act as admins
                else:
                    effective_role = self.user_type
            
            cache.set(cache_key, effective_role, timeout=300)  # 5 minutes
        
        return effective_role
    
    
    def clear_user_caches(self):
        """Clear all cached data for this user"""
        cache_keys = [
            f'user_profile_{self.id}',
            f'user_trust_connections_{self.id}',
            f'trust_network_size_{self.id}',
            f'user_under_network_{self.id}',
            f'user_admin_invitation_{self.id}',
            f'user_effective_role_{self.id}',
        ]
        cache.delete_many(cache_keys)
        
    def complete_onboarding_with_token(self, invitation_token):
        """Complete onboarding process with invitation token"""
        try:
            from invitations.models import OnboardingToken
            from invitations.tasks import process_invitation_acceptance
            
            # Process the invitation
            result = process_invitation_acceptance(invitation_token, str(self.id))
            
            if result['success']:
                # If user is owner, trigger defaults creation
                if self.user_type == 'owner':
                    from accounts.tasks import create_owner_defaults
                    create_owner_defaults.delay(str(self.id))
                else:
                    # For non-owners, just mark as active
                    self.status = 'active'
                    self.onboarding_completed = True
                    self.last_active_at = timezone.now()
                    self.save()
            
            return result
            
        except Exception as e:
            return {'success': False, 'error': str(e)}