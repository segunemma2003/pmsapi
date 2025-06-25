from rest_framework import serializers
from .models import Booking
from properties.serializers import PropertySerializer

class BookingSerializer(serializers.ModelSerializer):
    property_details = PropertySerializer(source='property', read_only=True)
    guest_name = serializers.CharField(source='guest.full_name', read_only=True)
    guest_email = serializers.CharField(source='guest.email', read_only=True)
    nights = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'property', 'property_details', 'guest', 'guest_name', 
            'guest_email', 'check_in_date', 'check_out_date', 'nights',
            'guests_count', 'total_amount', 'original_price', 'discount_applied',
            'status', 'special_requests', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'guest', 'total_amount', 'original_price', 
            'discount_applied', 'created_at', 'updated_at'
        ]
    
    def get_nights(self, obj):
        return (obj.check_out_date - obj.check_in_date).days

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
        
        # Check if property allows this many guests
        if attrs['guests_count'] > attrs['property'].max_guests:
            raise serializers.ValidationError("Too many guests for this property")
        
        return attrs
    
    def create(self, validated_data):
        validated_data['guest'] = self.context['request'].user
        return super().create(validated_data)