from rest_framework import serializers
from .models import Booking
from properties.serializers import PropertySerializer

class BookingSerializer(serializers.ModelSerializer):
    property_details = PropertySerializer(source='property', read_only=True)
    guest_name = serializers.CharField(source='guest.full_name', read_only=True)
    guest_email = serializers.CharField(source='guest.email', read_only=True)
    owner_name = serializers.CharField(source='property.owner.full_name', read_only=True)
    nights = serializers.SerializerMethodField()  # Changed to use SerializerMethodField
    can_approve = serializers.SerializerMethodField()
    can_reject = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'property', 'property_details', 'guest', 'guest_name', 
            'guest_email', 'owner_name', 'check_in_date', 'check_out_date', 
            'nights', 'guests_count', 'total_amount', 'original_price', 
            'discount_applied', 'status', 'status_display', 'special_requests',
            'requested_at', 'approved_at', 'rejected_at', 'rejection_reason',
            'beds24_booking_id', 'beds24_synced_at', 'beds24_sync_status',
            'can_approve', 'can_reject', 'can_cancel', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'guest', 'total_amount', 'original_price', 'discount_applied',
            'requested_at', 'approved_at', 'rejected_at', 'beds24_booking_id',
            'beds24_synced_at', 'beds24_sync_status', 'created_at', 'updated_at'
        ]
    
    def get_nights(self, obj):
        """Get nights using the model method"""
        return obj.get_nights()
    
    def get_can_approve(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return (obj.property.owner == request.user and obj.can_be_approved())
        return False
    
    def get_can_reject(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return (obj.property.owner == request.user and obj.can_be_rejected())
        return False
    
    def get_can_cancel(self, obj):
        request = self.context.get('request')
        if request and request.user:
            is_guest = obj.guest == request.user
            is_owner = obj.property.owner == request.user
            can_cancel_status = obj.status in ['pending', 'confirmed']
            return (is_guest or is_owner) and can_cancel_status
        return False

class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'property', 'check_in_date', 'check_out_date', 
            'guests_count', 'special_requests'
        ]
    
    def validate(self, attrs):
        if attrs['check_in_date'] >= attrs['check_out_date']:
            raise serializers.ValidationError("Check-out date must be after check-in date")
        
        from django.utils import timezone
        if attrs['check_in_date'] < timezone.now().date():
            raise serializers.ValidationError("Check-in date cannot be in the past")
        
        # Check if property allows this many guests
        if attrs['guests_count'] > attrs['property'].max_guests:
            raise serializers.ValidationError("Too many guests for this property")
        
        return attrs
    
    def create(self, validated_data):
        validated_data['guest'] = self.context['request'].user
        validated_data['status'] = 'pending'  # Always start as pending
        return super().create(validated_data)