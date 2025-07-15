from rest_framework import serializers
from django.contrib.auth import get_user_model
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
    response_time = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'summary', 'property_type', 'place_type',
            'city', 'state', 'country', 'display_price', 'bedrooms', 
            'bathrooms', 'max_guests', 'primary_image', 'is_featured',
            'owner_name', 'is_saved', 'amenity_count', 'instant_book_enabled',
            'response_time', 'created_at'
        ]
    
    def get_display_price(self, obj):
        """Get discounted price for the current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    def get_primary_image(self, obj):
        """Get the primary image URL"""
        primary_image = obj.images_set.filter(is_primary=True).first()
        if primary_image:
            return primary_image.image_url
        # Fallback to first image
        first_image = obj.images_set.first()
        return first_image.image_url if first_image else None
    
    def get_is_saved(self, obj):
        """Check if current user has saved this property"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedProperty.objects.filter(
                user=request.user,
                property=obj
            ).exists()
        return False
    
    def get_amenity_count(self, obj):
        """Get total number of amenities"""
        return len(obj.amenities)
    
    def get_response_time(self, obj):
        """Get owner's average response time (placeholder)"""
        return "Usually responds within 1 hour"
    
    
class PropertySerializer(serializers.ModelSerializer):
    """
    Full property serializer for detailed views
    """
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    display_price = serializers.SerializerMethodField()
    booking_count = serializers.SerializerMethodField()
    images = PropertyImageSerializer(source='images_set', many=True, read_only=True)
    is_saved = serializers.SerializerMethodField()
    amenity_categories = serializers.SerializerMethodField()
    price_breakdown = serializers.SerializerMethodField()
    
    class Meta:
        model = Property
        fields = [
            'id', 'title', 'description', 'summary', 'highlights',
            'property_type', 'place_type', 'address', 'city', 'state', 
            'country', 'postal_code', 'latitude', 'longitude', 'neighborhood',
            'transit_info', 'max_guests', 'bedrooms', 'beds', 'bathrooms',
            'square_feet', 'bed_configuration', 'amenities', 'amenity_categories',
            'safety_features', 'accessibility_features', 'house_rules',
            'smoking_allowed', 'pets_allowed', 'events_allowed', 'children_welcome',
            'quiet_hours_start', 'quiet_hours_end', 'price_per_night', 'display_price',
            'cleaning_fee', 'security_deposit', 'extra_guest_fee', 'extra_guest_threshold',
            'booking_type', 'minimum_stay', 'maximum_stay', 'booking_lead_time',
            'booking_window', 'check_in_time_start', 'check_in_time_end', 'check_out_time',
            'self_check_in', 'check_in_instructions', 'cancellation_policy',
            'guest_requirements', 'status', 'is_featured', 'is_visible',
            'instant_book_enabled', 'images', 'owner', 'owner_name', 'owner_email',
            'booking_count', 'beds24_property_id', 'ical_sync_enabled',
            'created_at', 'updated_at', 'is_saved', 'price_breakdown'
        ]
        read_only_fields = [
            'id', 'owner', 'beds24_property_id', 'created_at', 'updated_at', 
            'is_saved', 'booking_count', 'amenity_categories', 'price_breakdown'
        ]
    
    def get_display_price(self, obj):
        """Get discounted price for the current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_display_price(request.user)
        return obj.price_per_night
    
    def get_booking_count(self, obj):
        """Get total booking count"""
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
    
    def get_amenity_categories(self, obj):
        """Get categorized amenities"""
        if hasattr(obj, 'get_amenity_categories'):
            return obj.get_amenity_categories()
        return {}
    
    def get_price_breakdown(self, obj):
        """Get price breakdown for current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                return obj.get_total_price_breakdown(request.user)
            except:
                pass
        return {
            'base_price': float(obj.price_per_night),
            'cleaning_fee': float(obj.cleaning_fee),
            'security_deposit': float(obj.security_deposit),
            'service_fee': 0,
            'taxes': 0,
            'total': float(obj.price_per_night + obj.cleaning_fee + obj.security_deposit)
        }


class PropertyCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new properties
    """
    images = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        allow_empty=True
    )
    
    class Meta:
        model = Property
        fields = [
            'title', 'description', 'summary', 'property_type', 'place_type',
            'address', 'city', 'state', 'country', 'postal_code', 
            'latitude', 'longitude', 'neighborhood', 'max_guests', 
            'bedrooms', 'beds', 'bathrooms', 'square_feet',
            'bed_configuration', 'amenities', 'safety_features',
            'accessibility_features', 'house_rules', 'smoking_allowed',
            'pets_allowed', 'events_allowed', 'children_welcome',
            'quiet_hours_start', 'quiet_hours_end', 'price_per_night',
            'cleaning_fee', 'security_deposit', 'extra_guest_fee',
            'extra_guest_threshold', 'booking_type', 'minimum_stay',
            'maximum_stay', 'booking_lead_time', 'booking_window',
            'check_in_time_start', 'check_in_time_end', 'check_out_time',
            'self_check_in', 'check_in_instructions', 'cancellation_policy',
            'guest_requirements', 'is_visible', 'images'
        ]
    
    def create(self, validated_data):
        """Create property with images"""
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
    """
    Serializer for saved properties with property details
    """
    property = PropertyListSerializer(read_only=True)
    
    class Meta:
        model = SavedProperty
        fields = ['id', 'property', 'saved_at', 'notes']
        read_only_fields = ['id', 'saved_at']