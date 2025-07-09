from django.db import models
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
import uuid

User = get_user_model()


class TrustedNetworkInvitationManager(models.Manager):
    def get_valid_invitation(self, token):
        return self.filter(
            invitation_token=token,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
class TrustLevelDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trust_levels')
    level = models.PositiveIntegerField(db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    default_discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00
    )
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trust_level_definitions'
        unique_together = ['owner', 'level']
        indexes = [
            models.Index(fields=['owner', 'level']),
        ]
    
    @classmethod
    def create_default_levels(cls, owner):
        """Create default 5 trust levels for a new owner"""
        default_levels = [
            {'level': 1, 'name': 'Acquaintance', 'discount': 5.00, 'color': '#EF4444', 'desc': 'People you know casually'},
            {'level': 2, 'name': 'Friend', 'discount': 10.00, 'color': '#F97316', 'desc': 'Good friends you trust'},
            {'level': 3, 'name': 'Close Friend', 'discount': 15.00, 'color': '#EAB308', 'desc': 'Very close and trusted friends'},
            {'level': 4, 'name': 'Family Friend', 'discount': 20.00, 'color': '#22C55E', 'desc': 'Friends who are like family'},
            {'level': 5, 'name': 'Family', 'discount': 25.00, 'color': '#3B82F6', 'desc': 'Immediate and extended family'},
        ]
        
        levels = []
        for level_data in default_levels:
            level_obj = cls(
                owner=owner,
                level=level_data['level'],
                name=level_data['name'],
                description=level_data['desc'],
                default_discount_percentage=level_data['discount'],
                color=level_data['color']
            )
            levels.append(level_obj)
        
        cls.objects.bulk_create(levels)
        
        # Cache the levels
        cache_key = f'trust_levels_{owner.id}'
        cache.set(cache_key, levels, timeout=3600)  # 1 hour
        
        return levels

class OwnerTrustedNetworkManager(models.Manager):
    def get_user_networks(self, user):
        """Get all networks a user belongs to with caching"""
        cache_key = f'user_trust_networks_{user.id}'
        networks = cache.get(cache_key)
        
        if networks is None:
            networks = list(self.select_related('owner').filter(
                trusted_user=user,
                status='active'
            ).values(
                'owner__id', 'owner__full_name', 'trust_level', 
                'discount_percentage', 'added_at'
            ))
            cache.set(cache_key, networks, timeout=300)  # 5 minutes
        
        return networks

class OwnerTrustedNetwork(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('removed', 'Removed'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_networks')
    trusted_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_by')
    trust_level = models.PositiveIntegerField(db_index=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    notes = models.TextField(blank=True)
    invitation_id = models.UUIDField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = OwnerTrustedNetworkManager()
    
    class Meta:
        db_table = 'owner_trusted_networks'
        unique_together = ['owner', 'trusted_user']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['trusted_user', 'status']),
            models.Index(fields=['trust_level']),
            models.Index(fields=['added_at']),
        ]

class TrustedNetworkInvitation(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    )
    
    objects = TrustedNetworkInvitationManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='network_invitations')
    email = models.EmailField(db_index=True)
    invitee_name = models.CharField(max_length=255, blank=True)
    trust_level = models.PositiveIntegerField()
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    personal_message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trusted_network_invitations'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'email'],
                condition=models.Q(status='pending'),
                name='unique_pending_network_invitation'
            )
        ]
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

# Signal handlers for cache invalidation
@receiver(post_save, sender=OwnerTrustedNetwork)
def clear_trust_network_cache(sender, instance, **kwargs):
    """Clear relevant caches when trust network is updated"""
    cache.delete(f'trust_network_size_{instance.owner.id}')
    cache.delete(f'user_trust_networks_{instance.trusted_user.id}')
    cache.delete(f'trust_discount_{instance.owner.id}_{instance.trusted_user.id}')
    cache.delete(f'user_accessible_properties_{instance.trusted_user.id}')

@receiver(post_delete, sender=OwnerTrustedNetwork)
def clear_trust_network_cache_on_delete(sender, instance, **kwargs):
    """Clear caches when trust network is deleted"""
    cache.delete(f'trust_network_size_{instance.owner.id}')
    cache.delete(f'user_trust_networks_{instance.trusted_user.id}')
    cache.delete(f'trust_discount_{instance.owner.id}_{instance.trusted_user.id}')
    cache.delete(f'user_accessible_properties_{instance.trusted_user.id}')
