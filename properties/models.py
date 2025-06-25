from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
import uuid

User = get_user_model()

class Property(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved_pending_beds24', 'Approved Pending Beds24'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=255)
    description = models.TextField()
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    bedrooms = models.PositiveIntegerField()
    bathrooms = models.PositiveIntegerField()
    max_guests = models.PositiveIntegerField()
    images = ArrayField(models.URLField(), default=list, blank=True)
    amenities = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    
    # Beds24 Integration
    beds24_property_id = models.CharField(max_length=100, blank=True)
    beds24_sync_status = models.CharField(max_length=50, blank=True)
    beds24_sync_data = models.JSONField(default=dict, blank=True)
    beds24_synced_at = models.DateTimeField(null=True, blank=True)
    beds24_error_message = models.TextField(blank=True)
    
    # Approval tracking
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='approved_properties'
    )
    approval_notes = models.TextField(blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='rejected_properties'
    )
    rejection_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'properties'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status']),
            models.Index(fields=['city', 'status']),
            models.Index(fields=['beds24_property_id']),
            models.Index(fields=['created_at']),
        ]
    
    def get_discounted_price(self, user):
        """Get price with trust level discount applied"""
        if not user or not user.is_authenticated:
            return self.price_per_night
        
        # Check if user has trust level with this property's owner
        cache_key = f'trust_discount_{self.owner.id}_{user.id}'
        discount = cache.get(cache_key)
        
        if discount is None:
            from trust_levels.models import OwnerTrustedNetwork
            try:
                network = OwnerTrustedNetwork.objects.select_related('owner').get(
                    owner=self.owner,
                    trusted_user=user,
                    status='active'
                )
                discount = network.discount_percentage
            except OwnerTrustedNetwork.DoesNotExist:
                discount = 0
            
            cache.set(cache_key, discount, timeout=300)  # 5 minutes
        
        if discount > 0:
            discounted_price = self.price_per_night * (1 - (discount / 100))
            return round(discounted_price, 2)
        
        return self.price_per_night