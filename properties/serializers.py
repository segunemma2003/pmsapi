from rest_framework import serializers
from django.contrib.auth import get_user_model
from drf_yasg.utils import swagger_serializer_method
from drf_yasg import openapi
from .models import Property, PropertyImage, SavedProperty, PropertyAvailability

User = get_user_model()



class PropertyImageSerializer(serializers.ModelSerializer):
    """
    Serializer for property images with room categorization and captions
    """
    class Meta:
        model = PropertyImage
        fields = [
            'id', 'image_url', 'caption', 'is_primary', 
            'order', 'room_type', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
        
    def validate_image_url(self, value):
        """Validate that the image URL is accessible"""
        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError("Image URL must be a valid HTTP/HTTPS URL")
        return value
    
    
class PropertyAvailabilitySerializer(serializers.ModelSerializer):
    """
    Serializer for property availability and custom pricing
    """
    class Meta:
        model = PropertyAvailability
        fields = [
            'id', 'date', 'status', 'custom_price', 
            'minimum_stay', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    
class PropertyListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for property listings (search results, etc.)
    """
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    display_price = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    amenity_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'summary', 'property_type', 'place_type',
            'city', 'state', 'country', 'display_price', 'bedrooms', 
            'bathrooms', 'max_guests', 'primary_image', 'is_featured',
            'owner_name', 'is_saved', 'amenity_count', 'instant_book_enabled',
            'response_time', 'created_at'
        ]
    
    @swagger_serializer_method(serializer_or_field=serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_display_price(self, obj):
        """Get discounted price for the current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    @swagger_serializer_method(serializer_or_field=serializers.URLField())
    def get_primary_image(self, obj):
        """Get the primary image URL"""
        primary_image = obj.images_set.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image_url
        # Fallback to first image
        first_image = obj.images_set.first()
        return first_image.image_url if first_image else None
    
    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_is_saved(self, obj):
        """Check if current user has saved this property"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedProperty.objects.filter(
                user=request.user,
                property=obj
            ).exists()
        return False
    
    @swagger_serializer_method(serializer_or_field=serializers.IntegerField())
    def get_amenity_count(self, obj):
        """Get total number of amenities"""
        return len(obj.amenities)
    
    
class PropertyListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for property listings (search results, etc.)
    """
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    display_price = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    amenity_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'summary', 'property_type', 'place_type',
            'city', 'state', 'country', 'display_price', 'bedrooms', 
            'bathrooms', 'max_guests', 'primary_image', 'is_featured',
            'owner_name', 'is_saved', 'amenity_count', 'instant_book_enabled',
            'response_time', 'created_at'
        ]
    
    @swagger_serializer_method(serializer_or_field=serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_display_price(self, obj):
        """Get discounted price for the current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    @swagger_serializer_method(serializer_or_field=serializers.URLField())
    def get_primary_image(self, obj):
        """Get the primary image URL"""
        primary_image = obj.images_set.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image_url
        # Fallback to first image
        first_image = obj.images_set.first()
        return first_image.image_url if first_image else None
    
    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_is_saved(self, obj):
        """Check if current user has saved this property"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedProperty.objects.filter(
                user=request.user,
                property=obj
            ).exists()
        return False
    
    @swagger_serializer_method(serializer_or_field=serializers.IntegerField())
    def get_amenity_count(self, obj):
        """Get total number of amenities"""
        return len(obj.amenities)
    
    
class PropertySerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    display_price = serializers.SerializerMethodField()
    booking_count = serializers.SerializerMethodField()
    images = PropertyImageSerializer(source='images_set', many=True, read_only=True)
    is_saved = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'address', 'city', 'state', 
            'country', 'display_price', 'bedrooms', 'bathrooms', 'max_guests', 
            'images', 'amenities', 'status', 'is_featured', 'is_visible',
            'owner', 'owner_name', 'booking_count', 'beds24_property_id', 
            'ical_sync_enabled', 'created_at', 'updated_at', 'is_saved'
        ]
        read_only_fields = [
            'id', 'owner', 'beds24_property_id', 'created_at', 'updated_at', 'is_saved'
        ]
    
    def get_display_price(self, obj):
        """Always return the discounted price (user should never see original price)"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    def get_booking_count(self, obj):
        return getattr(obj, 'booking_count', 0)
    
    def get_is_saved(self, obj):
        """Check if current user has saved this property"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedProperty.objects.filter(
                user=request.user,
                property=obj
            ).exists()
        return False


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
    

class SavedPropertySerializer(serializers.ModelSerializer):
    """Serializer for saved properties with property details"""
    property = PropertySerializer(read_only=True)
    
    class Meta:
        model = SavedProperty
        fields = ['id', 'property', 'saved_at', 'notes']
        read_only_fields = ['id', 'saved_at']