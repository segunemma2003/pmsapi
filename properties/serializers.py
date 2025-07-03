from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Property, PropertyImage

User = get_user_model()



class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'image_url', 'is_primary', 'order']
class PropertySerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    display_price = serializers.SerializerMethodField()
    booking_count = serializers.SerializerMethodField()
    images = PropertyImageSerializer(source='images_set', many=True, read_only=True)
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'address', 'city', 'state', 
            'country', 'display_price', 'bedrooms', 'bathrooms', 'max_guests', 
            'images', 'amenities', 'status', 'is_featured', 'is_visible',
            'owner', 'owner_name', 'booking_count', 'beds24_property_id', 
            'ical_sync_enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'beds24_property_id', 'created_at', 'updated_at'
        ]
    
    def get_display_price(self, obj):
        """Always return the discounted price (user should never see original price)"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    def get_booking_count(self, obj):
        return getattr(obj, 'booking_count', 0)


class PropertyCreateSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        allow_empty=True
    )
    
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'address', 'city', 'state', 
            'country', 'postal_code', 'latitude', 'longitude',
            'price_per_night', 'bedrooms', 'bathrooms', 'max_guests', 
            'images', 'amenities', 'is_visible'
        ]
    
    def create(self, validated_data):
        images_data = validated_data.pop('images', [])
        validated_data['owner'] = self.context['request'].user
        validated_data['status'] = 'active'  # Auto-active, no approval needed
        
        property_obj = Property.objects.create(**validated_data)
        
        # Create property images
        for idx, image_url in enumerate(images_data):
            PropertyImage.objects.create(
                property=property_obj,
                image_url=image_url,
                is_primary=(idx == 0),
                order=idx
            )
        
        return property_obj
    
