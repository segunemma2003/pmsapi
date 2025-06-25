from rest_framework import serializers
from .models import Property
from django.contrib.auth import get_user_model

User = get_user_model()

class PropertySerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    discounted_price = serializers.SerializerMethodField()
    booking_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'address', 'city', 'state', 
            'country', 'price_per_night', 'discounted_price', 'bedrooms', 
            'bathrooms', 'max_guests', 'images', 'amenities', 'status',
            'is_featured', 'owner', 'owner_name', 'booking_count',
            'beds24_property_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'status', 'beds24_property_id', 
            'created_at', 'updated_at'
        ]
    
    def get_discounted_price(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_discounted_price(request.user)
        return obj.price_per_night
    
    def get_booking_count(self, obj):
        return obj.bookings.count()

class PropertyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'address', 'city', 'state', 
            'country', 'postal_code', 'latitude', 'longitude',
            'price_per_night', 'bedrooms', 'bathrooms', 'max_guests', 
            'images', 'amenities'
        ]
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)