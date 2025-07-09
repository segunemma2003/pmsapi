from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import uuid

User = get_user_model()

class Property(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, db_index=True)
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    bedrooms = models.PositiveIntegerField(db_index=True)
    bathrooms = models.PositiveIntegerField()
    max_guests = models.PositiveIntegerField(db_index=True)
    amenities = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active', db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_visible = models.BooleanField(default=True, db_index=True)  # Owner can control visibility
    
    # Beds24 Integration
    beds24_property_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    beds24_sync_status = models.CharField(max_length=50, blank=True)
    beds24_sync_data = models.JSONField(default=dict, blank=True)
    beds24_synced_at = models.DateTimeField(null=True, blank=True)
    beds24_error_message = models.TextField(blank=True)
    
    # iCal Integration Fields
    ical_import_url = models.URLField(blank=True)
    ical_export_url = models.URLField(blank=True)
    ical_sync_enabled = models.BooleanField(default=True)
    ical_last_sync = models.DateTimeField(null=True, blank=True)
    ical_sync_status = models.CharField(max_length=50, blank=True)
    ical_external_calendars = models.JSONField(default=list, blank=True)
    ical_sync_interval = models.PositiveIntegerField(default=3600)
    ical_auto_block = models.BooleanField(default=True)
    ical_timezone = models.CharField(max_length=50, default='UTC')
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'properties'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'is_visible']),
            models.Index(fields=['city', 'status', 'is_visible']),
            models.Index(fields=['price_per_night', 'status', 'is_visible']),
            models.Index(fields=['created_at']),
        ]
    
    def get_display_price(self, user):
        """Get the price that should be displayed to user (always discounted price)"""
        if not user or not user.is_authenticated or user.user_type == 'admin':
            return self.price_per_night
        
        # For property owners, no discount on their own properties
        if user == self.owner:
            return self.price_per_night
        
        # Check cache first
        cache_key = f'trust_discount_{self.owner.id}_{user.id}'
        discount = cache.get(cache_key)
        
        if discount is None:
            from trust_levels.models import OwnerTrustedNetwork
            try:
                network = OwnerTrustedNetwork.objects.get(
                    owner=self.owner,
                    trusted_user=user,
                    status='active'
                )
                discount = float(network.discount_percentage)
            except OwnerTrustedNetwork.DoesNotExist:
                discount = 0
            
            cache.set(cache_key, discount, timeout=300)  # 5 minutes
        
        if discount > 0:
            # Convert discount to Decimal to avoid type mismatch
            discount_decimal = Decimal(str(discount))
            discount_multiplier = Decimal('1') - (discount_decimal / Decimal('100'))
            discounted_price = self.price_per_night * discount_multiplier
            return discounted_price.quantize(Decimal('0.01'))  # Round to 2 decimal places
        
        return self.price_per_night

# Signal to automatically queue property for Beds24 after creation
@receiver(post_save, sender=Property)
def auto_queue_beds24_sync(sender, instance, created, **kwargs):
    """Automatically queue new properties for Beds24 sync"""
    if created and instance.status == 'active':
        from .tasks import enlist_to_beds24
        # Queue for Beds24 integration
        enlist_to_beds24.delay(str(instance.id))


class PropertyImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images_set')
    image_url = models.URLField()
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'property_images'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['property', 'is_primary']),
            models.Index(fields=['order']),
        ]