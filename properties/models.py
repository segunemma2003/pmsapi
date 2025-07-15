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
    # Property Types
    PROPERTY_TYPE_CHOICES = (
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('cabin', 'Cabin'),
        ('villa', 'Villa'),
        ('condo', 'Condo'),
        ('townhouse', 'Townhouse'),
        ('loft', 'Loft'),
        ('castle', 'Castle'),
        ('treehouse', 'Treehouse'),
        ('boat', 'Boat'),
        ('camper', 'Camper/RV'),
        ('tent', 'Tent'),
        ('other', 'Other'),
    )
    
    PLACE_TYPE_CHOICES = (
        ('entire_place', 'Entire place'),
        ('private_room', 'Private room'),
        ('shared_room', 'Shared room'),
    )
    
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    BOOKING_TYPE_CHOICES = (
        ('instant', 'Instant Book'),
        ('request', 'Request to Book'),
    )
    
    CANCELLATION_POLICY_CHOICES = (
        ('flexible', 'Flexible'),
        ('moderate', 'Moderate'),
        ('strict', 'Strict'),
        ('super_strict_30', 'Super Strict 30'),
        ('super_strict_60', 'Super Strict 60'),
    )
    
    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='properties')
    
    # Property Type & Category
    property_type = models.CharField(max_length=50, choices=PROPERTY_TYPE_CHOICES, db_index=True)
    place_type = models.CharField(max_length=20, choices=PLACE_TYPE_CHOICES, db_index=True)
    
    # Title & Description
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    summary = models.TextField(max_length=500, blank=True)  # Short summary for listings
    highlights = ArrayField(models.CharField(max_length=100), default=list, blank=True)  # Key selling points
    
    # Location Details
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, db_index=True)
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    neighborhood = models.CharField(max_length=100, blank=True)  # Area/neighborhood name
    transit_info = models.TextField(blank=True)  # Public transport information
    
    # Space Details
    max_guests = models.PositiveIntegerField(db_index=True)
    bedrooms = models.PositiveIntegerField(db_index=True)
    beds = models.PositiveIntegerField()  # Total number of beds
    bathrooms = models.DecimalField(max_digits=3, decimal_places=1)  # Allow half bathrooms
    square_feet = models.PositiveIntegerField(null=True, blank=True)
    
    # Bed Configuration (JSON field for detailed bed info)
    bed_configuration = models.JSONField(default=dict, blank=True)  # e.g., {"bedroom1": {"king": 1}, "living_room": {"sofa": 1}}
    
    # Amenities & Features
    amenities = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    safety_features = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    accessibility_features = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    
    # House Rules
    house_rules = models.TextField(blank=True)
    smoking_allowed = models.BooleanField(default=False)
    pets_allowed = models.BooleanField(default=False)
    events_allowed = models.BooleanField(default=False)
    children_welcome = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    
    # Pricing
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    cleaning_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    security_deposit = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    extra_guest_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0)  # Per guest beyond base
    extra_guest_threshold = models.PositiveIntegerField(default=0)  # Number of guests before extra fee applies
    
    # Note: Weekly/monthly discounts will be handled through a separate promotions system
    
    # Booking Settings
    booking_type = models.CharField(max_length=20, choices=BOOKING_TYPE_CHOICES, default='request')
    minimum_stay = models.PositiveIntegerField(default=1)  # Nights
    maximum_stay = models.PositiveIntegerField(default=365)  # Nights
    booking_lead_time = models.PositiveIntegerField(default=0)  # Days in advance required
    booking_window = models.PositiveIntegerField(default=365)  # How far in advance can book
    
    # Check-in/out
    check_in_time_start = models.TimeField(default='15:00')
    check_in_time_end = models.TimeField(default='20:00')
    check_out_time = models.TimeField(default='11:00')
    self_check_in = models.BooleanField(default=False)
    check_in_instructions = models.TextField(blank=True)
    
    # Cancellation Policy
    cancellation_policy = models.CharField(max_length=20, choices=CANCELLATION_POLICY_CHOICES, default='moderate')
    
    # Guest Requirements
    guest_requirements = models.JSONField(default=dict, blank=True)  # e.g., {"verified_id": true, "phone": true}
    
    # Status & Visibility
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='active', db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_visible = models.BooleanField(default=True, db_index=True)
    instant_book_enabled = models.BooleanField(default=False)
    
    # Professional Hosting
    professional_hosting_tools = models.BooleanField(default=False)
    multi_calendar = models.BooleanField(default=False)
    professional_photos = models.BooleanField(default=False)
    
    # Legal & Compliance
    local_laws_compliant = models.BooleanField(default=False)
    business_license = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    
    # Note: Performance metrics will be calculated dynamically from booking interactions
    
    # Beds24 Integration (existing)
    beds24_property_id = models.CharField(max_length=100, blank=True, unique=True, null=True)
    beds24_sync_status = models.CharField(max_length=50, blank=True)
    beds24_sync_data = models.JSONField(default=dict, blank=True)
    beds24_synced_at = models.DateTimeField(null=True, blank=True)
    beds24_error_message = models.TextField(blank=True)
    
    # iCal Integration (existing)
    ical_import_url = models.URLField(blank=True)
    ical_export_url = models.URLField(blank=True)
    ical_sync_enabled = models.BooleanField(default=True)
    ical_last_sync = models.DateTimeField(null=True, blank=True)
    ical_sync_status = models.CharField(max_length=50, blank=True)
    ical_external_calendars = models.JSONField(default=list, blank=True)
    ical_sync_interval = models.PositiveIntegerField(default=3600)
    ical_auto_block = models.BooleanField(default=True)
    ical_timezone = models.CharField(max_length=50, default='UTC')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_published_at = models.DateTimeField(null=True, blank=True)
    last_booked_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'properties'
        indexes = [
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['status', 'is_visible']),
            models.Index(fields=['city', 'status', 'is_visible']),
            models.Index(fields=['price_per_night', 'status', 'is_visible']),
            models.Index(fields=['property_type', 'place_type']),
            models.Index(fields=['max_guests', 'bedrooms']),
            models.Index(fields=['booking_type', 'instant_book_enabled']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.city}"
    
    def get_display_price(self, user, nights=1, guests=1):
        """Get the price that should be displayed to user including all fees"""
        if not user or not user.is_authenticated or user.user_type == 'admin':
            base_price = self.price_per_night * nights
        elif user == self.owner:
            base_price = self.price_per_night * nights
        else:
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
                
                cache.set(cache_key, discount, timeout=300)
            
            if discount > 0:
                discount_decimal = Decimal(str(discount))
                discount_multiplier = Decimal('1') - (discount_decimal / Decimal('100'))
                discounted_nightly = self.price_per_night * discount_multiplier
                base_price = discounted_nightly * nights
            else:
                base_price = self.price_per_night * nights
        
        # Add extra guest fees
        if guests > self.extra_guest_threshold and self.extra_guest_fee > 0:
            extra_guests = guests - self.extra_guest_threshold
            extra_guest_total = self.extra_guest_fee * extra_guests * nights
            base_price += extra_guest_total
        
        # Apply weekly/monthly discounts (calculated from promotions system)
        # This will be handled by a separate promotions/pricing system
        
        return base_price.quantize(Decimal('0.01'))
    
    def get_total_price_breakdown(self, user, nights=1, guests=1):
        """Get detailed price breakdown"""
        base_price = self.get_display_price(user, nights, guests)
        
        breakdown = {
            'base_price': float(base_price),
            'cleaning_fee': float(self.cleaning_fee),
            'security_deposit': float(self.security_deposit),
            'service_fee': 0,  # Platform service fee (if applicable)
            'taxes': 0,  # Local taxes (if applicable)
            'total': float(base_price + self.cleaning_fee + self.security_deposit)
        }
        
        return breakdown
    
    def get_amenity_categories(self):
        """Categorize amenities for better display"""
        categories = {
            'wifi_workspace': [],
            'kitchen_dining': [],
            'entertainment': [],
            'family': [],
            'safety': [],
            'accessibility': [],
            'outdoor': [],
            'parking': [],
            'other': []
        }
        
        amenity_mapping = {
            'wifi': 'wifi_workspace',
            'workspace': 'wifi_workspace',
            'kitchen': 'kitchen_dining',
            'breakfast': 'kitchen_dining',
            'tv': 'entertainment',
            'netflix': 'entertainment',
            'crib': 'family',
            'high_chair': 'family',
            'smoke_alarm': 'safety',
            'carbon_monoxide_alarm': 'safety',
            'wheelchair_accessible': 'accessibility',
            'patio': 'outdoor',
            'garden': 'outdoor',
            'parking': 'parking',
            'garage': 'parking',
        }
        
        for amenity in self.amenities:
            category = amenity_mapping.get(amenity.lower(), 'other')
            categories[category].append(amenity)
        
        return {k: v for k, v in categories.items() if v}  # Only return non-empty categories


class PropertyImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images_set')
    image_url = models.URLField()
    caption = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    room_type = models.CharField(max_length=50, blank=True)  # bedroom, bathroom, kitchen, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'property_images'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['property', 'is_primary']),
            models.Index(fields=['order']),
        ]


class PropertyAvailability(models.Model):
    """Track custom pricing and availability"""
    AVAILABILITY_CHOICES = (
        ('available', 'Available'),
        ('blocked', 'Blocked'),
        ('reserved', 'Reserved'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='availability_set')
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='available')
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_stay = models.PositiveIntegerField(null=True, blank=True)  # Override property minimum
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'property_availability'
        unique_together = ['property', 'date']
        indexes = [
            models.Index(fields=['property', 'date', 'status']),
            models.Index(fields=['date', 'status']),
        ]


class SavedProperty(models.Model):
    """Model to track properties saved/bookmarked by users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_properties')
    property = models.ForeignKey('Property', on_delete=models.CASCADE, related_name='saved_by_users')
    saved_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        db_table = 'saved_properties'
        unique_together = ['user', 'property']
        indexes = [
            models.Index(fields=['user', 'saved_at']),
            models.Index(fields=['property']),
            models.Index(fields=['saved_at']),
        ]
        ordering = ['-saved_at']


# Signal to automatically queue property for Beds24 after creation
@receiver(post_save, sender=Property)
def auto_queue_beds24_sync(sender, instance, created, **kwargs):
    """Automatically queue new properties for Beds24 sync"""
    if created and instance.status == 'active':
        from .tasks import enlist_to_beds24
        enlist_to_beds24.delay(str(instance.id))