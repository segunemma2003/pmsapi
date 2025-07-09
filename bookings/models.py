from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Booking(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),      # Initial status when user makes request
        ('confirmed', 'Confirmed'),           # Owner approved
        ('rejected', 'Rejected'),             # Owner rejected  
        ('cancelled', 'Cancelled'),           # Cancelled after confirmation
        ('completed', 'Completed'),           # Stay completed
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey('properties.Property', on_delete=models.CASCADE, related_name='bookings')
    guest = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    guests_count = models.PositiveIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_applied = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    special_requests = models.TextField(blank=True)
    booking_metadata = models.JSONField(default=dict, blank=True)
    
    # New fields for approval workflow
    requested_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)  # When guest made request
    approved_at = models.DateTimeField(null=True, blank=True)  # When owner approved
    rejected_at = models.DateTimeField(null=True, blank=True)  # When owner rejected
    rejection_reason = models.TextField(blank=True)  # Why owner rejected
    
    # Beds24 sync tracking
    beds24_booking_id = models.CharField(max_length=100, blank=True)
    beds24_synced_at = models.DateTimeField(null=True, blank=True)
    beds24_sync_status = models.CharField(max_length=50, blank=True)
    beds24_sync_error = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bookings'
        indexes = [
            models.Index(fields=['guest', 'status']),
            models.Index(fields=['property', 'status']),
            models.Index(fields=['check_in_date']),
            models.Index(fields=['check_out_date']),
            models.Index(fields=['status', 'requested_at']),
            models.Index(fields=['created_at']),
        ]
    
    def save(self, *args, **kwargs):
        # Calculate pricing if not set
        if not self.total_amount and self.property:
            nights = (self.check_out_date - self.check_in_date).days
            discounted_price = self.property.get_display_price(self.guest)
            
            self.original_price = self.property.price_per_night * nights
            self.total_amount = discounted_price * nights
            
            # Calculate discount percentage
            if self.original_price > 0:
                self.discount_applied = ((self.original_price - self.total_amount) / self.original_price) * 100
        
        super().save(*args, **kwargs)
    
    def can_be_approved(self):
        """Check if booking can be approved"""
        return self.status == 'pending'
    
    def can_be_rejected(self):
        """Check if booking can be rejected"""
        return self.status == 'pending'
    
    def get_nights(self):
        """Calculate number of nights - using method instead of @property to avoid conflict"""
        return (self.check_out_date - self.check_in_date).days