from django.db import models
from django.contrib.auth import get_user_model
from django.core.cache import cache
import uuid

User = get_user_model()

class TrustLevelDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trust_levels')
    level = models.PositiveIntegerField()
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
            {'level': 1, 'name': 'Acquaintance', 'discount': 5.00, 'color': '#EF4444'},
            {'level': 2, 'name': 'Friend', 'discount': 10.00, 'color': '#F97316'},
            {'level': 3, 'name': 'Close Friend', 'discount': 15.00, 'color': '#EAB308'},
            {'level': 4, 'name': 'Family Friend', 'discount': 20.00, 'color': '#22C55E'},
            {'level': 5, 'name': 'Family', 'discount': 25.00, 'color': '#3B82F6'},
        ]
        
        levels = []
        for level_data in default_levels:
            levels.append(cls(
                owner=owner,
                level=level_data['level'],
                name=level_data['name'],
                default_discount_percentage=level_data['discount'],
                color=level_data['color']
            ))
        
        cls.objects.bulk_create(levels)
        
        # Cache the levels
        cache_key = f'trust_levels_{owner.id}'
        cache.set(cache_key, levels, timeout=3600)  # 1 hour
        
        return levels

class OwnerTrustedNetwork(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('removed', 'Removed'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_networks')
    trusted_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_by')
    trust_level = models.PositiveIntegerField()
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    invitation_id = models.UUIDField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'owner_trusted_networks'
        unique_together = ['owner', 'trusted_user']
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['trusted_user', 'status']),
            models.Index(fields=['trust_level']),
        ]
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Clear relevant caches
        cache.delete(f'trust_network_size_{self.owner.id}')
        cache.delete(f'user_trust_levels_{self.trusted_user.id}')

class TrustedNetworkInvitation(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='network_invitations')
    email = models.EmailField()
    invitee_name = models.CharField(max_length=255, blank=True)
    trust_level = models.PositiveIntegerField()
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    personal_message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    invitation_token = models.UUIDField(default=uuid.uuid4, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trusted_network_invitations'
        indexes = [
            models.Index(fields=['invitation_token']),
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['expires_at']),
        ]