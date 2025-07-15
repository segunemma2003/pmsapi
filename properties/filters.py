import django_filters
from django.db.models import Q
from .models import Property, PropertyAvailability, PropertyImage, SavedProperty

class PropertyFilter(django_filters.FilterSet):
    # Location filters
    city = django_filters.CharFilter(lookup_expr='icontains')
    state = django_filters.CharFilter(lookup_expr='icontains')
    country = django_filters.CharFilter(lookup_expr='icontains')
    neighborhood = django_filters.CharFilter(lookup_expr='icontains')
    
    # Price filters
    price_min = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='lte')
    price_range = django_filters.RangeFilter(field_name='price_per_night')
    
    # Space filters
    bedrooms = django_filters.NumberFilter(field_name='bedrooms', lookup_expr='exact')
    bedrooms_min = django_filters.NumberFilter(field_name='bedrooms', lookup_expr='gte')
    bedrooms_max = django_filters.NumberFilter(field_name='bedrooms', lookup_expr='lte')
    
    bathrooms = django_filters.NumberFilter(field_name='bathrooms', lookup_expr='exact')
    bathrooms_min = django_filters.NumberFilter(field_name='bathrooms', lookup_expr='gte')
    
    max_guests = django_filters.NumberFilter(field_name='max_guests', lookup_expr='exact')
    max_guests_min = django_filters.NumberFilter(field_name='max_guests', lookup_expr='gte')
    max_guests_max = django_filters.NumberFilter(field_name='max_guests', lookup_expr='lte')
    
    beds = django_filters.NumberFilter(field_name='beds', lookup_expr='exact')
    beds_min = django_filters.NumberFilter(field_name='beds', lookup_expr='gte')
    
    square_feet_min = django_filters.NumberFilter(field_name='square_feet', lookup_expr='gte')
    square_feet_max = django_filters.NumberFilter(field_name='square_feet', lookup_expr='lte')
    
    # Property type filters
    property_type = django_filters.ChoiceFilter(choices=Property.PROPERTY_TYPE_CHOICES)
    place_type = django_filters.ChoiceFilter(choices=Property.PLACE_TYPE_CHOICES)
    
    # Amenities filter
    amenities = django_filters.CharFilter(method='filter_amenities')
    has_wifi = django_filters.BooleanFilter(method='filter_has_wifi')
    has_kitchen = django_filters.BooleanFilter(method='filter_has_kitchen')
    has_parking = django_filters.BooleanFilter(method='filter_has_parking')
    has_pool = django_filters.BooleanFilter(method='filter_has_pool')
    has_ac = django_filters.BooleanFilter(method='filter_has_ac')
    has_tv = django_filters.BooleanFilter(method='filter_has_tv')
    has_washer = django_filters.BooleanFilter(method='filter_has_washer')
    has_dryer = django_filters.BooleanFilter(method='filter_has_dryer')
    has_gym = django_filters.BooleanFilter(method='filter_has_gym')
    has_balcony = django_filters.BooleanFilter(method='filter_has_balcony')
    
    # Booking settings
    booking_type = django_filters.ChoiceFilter(choices=Property.BOOKING_TYPE_CHOICES)
    instant_book = django_filters.BooleanFilter(field_name='instant_book_enabled')
    minimum_stay = django_filters.NumberFilter(field_name='minimum_stay', lookup_expr='exact')
    minimum_stay_max = django_filters.NumberFilter(field_name='minimum_stay', lookup_expr='lte')
    maximum_stay_min = django_filters.NumberFilter(field_name='maximum_stay', lookup_expr='gte')
    
    # Policies
    pets_allowed = django_filters.BooleanFilter()
    smoking_allowed = django_filters.BooleanFilter()
    events_allowed = django_filters.BooleanFilter()
    children_welcome = django_filters.BooleanFilter()
    self_check_in = django_filters.BooleanFilter()
    
    # Cancellation policy
    cancellation_policy = django_filters.ChoiceFilter(choices=Property.CANCELLATION_POLICY_CHOICES)
    
    # Status and visibility
    status = django_filters.ChoiceFilter(choices=Property.STATUS_CHOICES)
    is_featured = django_filters.BooleanFilter()
    is_visible = django_filters.BooleanFilter()
    
    # Owner filter
    owner = django_filters.UUIDFilter(field_name='owner__id')
    owner_name = django_filters.CharFilter(field_name='owner__full_name', lookup_expr='icontains')
    
    # Date filters
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    updated_after = django_filters.DateFilter(field_name='updated_at', lookup_expr='date__gte')
    updated_before = django_filters.DateFilter(field_name='updated_at', lookup_expr='date__lte')
    
    # Price range filters
    cleaning_fee_max = django_filters.NumberFilter(field_name='cleaning_fee', lookup_expr='lte')
    security_deposit_max = django_filters.NumberFilter(field_name='security_deposit', lookup_expr='lte')
    
    # Geographic filters
    has_coordinates = django_filters.BooleanFilter(method='filter_has_coordinates')
    
    # Text search
    search = django_filters.CharFilter(method='filter_search')
    title_search = django_filters.CharFilter(field_name='title', lookup_expr='icontains')
    description_search = django_filters.CharFilter(field_name='description', lookup_expr='icontains')
    
    # Ordering
    ordering = django_filters.OrderingFilter(
        fields=(
            ('price_per_night', 'price'),
            ('created_at', 'created'),
            ('updated_at', 'updated'),
            ('title', 'title'),
            ('max_guests', 'guests'),
            ('bedrooms', 'bedrooms'),
            ('bathrooms', 'bathrooms'),
            ('beds', 'beds'),
            ('square_feet', 'size'),
        ),
        field_labels={
            'price_per_night': 'Price per night',
            'created_at': 'Date created',
            'updated_at': 'Date updated',
            'title': 'Title',
            'max_guests': 'Guest capacity',
            'bedrooms': 'Number of bedrooms',
            'bathrooms': 'Number of bathrooms',
            'beds': 'Number of beds',
            'square_feet': 'Property size',
        }
    )
    
    class Meta:
        model = Property
        fields = [
            'status', 'is_featured', 'is_visible', 'owner',
            'property_type', 'place_type', 'booking_type',
            'pets_allowed', 'smoking_allowed', 'events_allowed',
            'children_welcome', 'instant_book_enabled', 'self_check_in',
            'cancellation_policy'
        ]
    
    def filter_amenities(self, queryset, name, value):
        """Filter properties that have specific amenities"""
        if value:
            amenities_list = [amenity.strip() for amenity in value.split(',')]
            for amenity in amenities_list:
                queryset = queryset.filter(amenities__icontains=amenity)
        return queryset
    
    def filter_has_wifi(self, queryset, name, value):
        """Filter properties with WiFi"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='wifi') | 
                Q(amenities__icontains='internet') |
                Q(amenities__icontains='wireless') |
                Q(amenities__icontains='wi-fi')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='wifi') | 
                Q(amenities__icontains='internet') |
                Q(amenities__icontains='wireless') |
                Q(amenities__icontains='wi-fi')
            )
        return queryset
    
    def filter_has_kitchen(self, queryset, name, value):
        """Filter properties with kitchen"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='kitchen') |
                Q(amenities__icontains='kitchenette') |
                Q(amenities__icontains='cooking') |
                Q(amenities__icontains='microwave') |
                Q(amenities__icontains='stove')
            )
        return queryset
    
    def filter_has_parking(self, queryset, name, value):
        """Filter properties with parking"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='parking') |
                Q(amenities__icontains='garage') |
                Q(amenities__icontains='driveway') |
                Q(amenities__icontains='car park')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='parking') |
                Q(amenities__icontains='garage') |
                Q(amenities__icontains='driveway') |
                Q(amenities__icontains='car park')
            )
        return queryset
    
    def filter_has_pool(self, queryset, name, value):
        """Filter properties with pool"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='pool') |
                Q(amenities__icontains='swimming') |
                Q(amenities__icontains='jacuzzi') |
                Q(amenities__icontains='hot tub')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='pool') |
                Q(amenities__icontains='swimming') |
                Q(amenities__icontains='jacuzzi') |
                Q(amenities__icontains='hot tub')
            )
        return queryset
    
    def filter_has_ac(self, queryset, name, value):
        """Filter properties with air conditioning"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='air conditioning') |
                Q(amenities__icontains='ac') |
                Q(amenities__icontains='climate control') |
                Q(amenities__icontains='cooling')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='air conditioning') |
                Q(amenities__icontains='ac') |
                Q(amenities__icontains='climate control') |
                Q(amenities__icontains='cooling')
            )
        return queryset
    
    def filter_has_tv(self, queryset, name, value):
        """Filter properties with TV"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='tv') |
                Q(amenities__icontains='television') |
                Q(amenities__icontains='cable') |
                Q(amenities__icontains='netflix') |
                Q(amenities__icontains='streaming')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='tv') |
                Q(amenities__icontains='television') |
                Q(amenities__icontains='cable') |
                Q(amenities__icontains='netflix') |
                Q(amenities__icontains='streaming')
            )
        return queryset
    
    def filter_has_washer(self, queryset, name, value):
        """Filter properties with washer"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='washer') |
                Q(amenities__icontains='washing machine') |
                Q(amenities__icontains='laundry')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='washer') |
                Q(amenities__icontains='washing machine') |
                Q(amenities__icontains='laundry')
            )
        return queryset
    
    def filter_has_dryer(self, queryset, name, value):
        """Filter properties with dryer"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='dryer') |
                Q(amenities__icontains='drying machine')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='dryer') |
                Q(amenities__icontains='drying machine')
            )
        return queryset
    
    def filter_has_gym(self, queryset, name, value):
        """Filter properties with gym/fitness facilities"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='gym') |
                Q(amenities__icontains='fitness') |
                Q(amenities__icontains='exercise') |
                Q(amenities__icontains='workout')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='gym') |
                Q(amenities__icontains='fitness') |
                Q(amenities__icontains='exercise') |
                Q(amenities__icontains='workout')
            )
        return queryset
    
    def filter_has_balcony(self, queryset, name, value):
        """Filter properties with balcony/terrace"""
        if value:
            return queryset.filter(
                Q(amenities__icontains='balcony') |
                Q(amenities__icontains='terrace') |
                Q(amenities__icontains='patio') |
                Q(amenities__icontains='deck') |
                Q(amenities__icontains='outdoor space')
            )
        elif value is False:
            return queryset.exclude(
                Q(amenities__icontains='balcony') |
                Q(amenities__icontains='terrace') |
                Q(amenities__icontains='patio') |
                Q(amenities__icontains='deck') |
                Q(amenities__icontains='outdoor space')
            )
        return queryset
    
    def filter_has_coordinates(self, queryset, name, value):
        """Filter properties that have geographic coordinates"""
        if value:
            return queryset.filter(
                latitude__isnull=False,
                longitude__isnull=False
            )
        elif value is False:
            return queryset.filter(
                Q(latitude__isnull=True) |
                Q(longitude__isnull=True)
            )
        return queryset
    
    def filter_search(self, queryset, name, value):
        """Full text search across multiple fields"""
        if value:
            search_terms = value.split()
            query = Q()
            
            for term in search_terms:
                term_query = (
                    Q(title__icontains=term) |
                    Q(description__icontains=term) |
                    Q(summary__icontains=term) |
                    Q(city__icontains=term) |
                    Q(state__icontains=term) |
                    Q(country__icontains=term) |
                    Q(neighborhood__icontains=term) |
                    Q(address__icontains=term) |
                    Q(amenities__icontains=term) |
                    Q(highlights__icontains=term) |
                    Q(property_type__icontains=term) |
                    Q(place_type__icontains=term)
                )
                query &= term_query
            
            return queryset.filter(query).distinct()
        return queryset


class PropertyAvailabilityFilter(django_filters.FilterSet):
    """Filter for PropertyAvailability model"""
    from .models import PropertyAvailability
    
    property = django_filters.UUIDFilter(field_name='property__id')
    date = django_filters.DateFilter()
    date_after = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_before = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    date_range = django_filters.DateRangeFilter(field_name='date')
    status = django_filters.ChoiceFilter(choices=PropertyAvailability.AVAILABILITY_CHOICES)
    has_custom_price = django_filters.BooleanFilter(method='filter_has_custom_price')
    custom_price_min = django_filters.NumberFilter(field_name='custom_price', lookup_expr='gte')
    custom_price_max = django_filters.NumberFilter(field_name='custom_price', lookup_expr='lte')
    
    class Meta:
        model = PropertyAvailability
        fields = ['property', 'date', 'status']
    
    def filter_has_custom_price(self, queryset, name, value):
        """Filter availability entries with custom pricing"""
        if value:
            return queryset.filter(custom_price__isnull=False)
        elif value is False:
            return queryset.filter(custom_price__isnull=True)
        return queryset


class SavedPropertyFilter(django_filters.FilterSet):
    """Filter for SavedProperty model"""
    from .models import SavedProperty
    
    user = django_filters.UUIDFilter(field_name='user__id')
    property = django_filters.UUIDFilter(field_name='property__id')
    saved_after = django_filters.DateTimeFilter(field_name='saved_at', lookup_expr='gte')
    saved_before = django_filters.DateTimeFilter(field_name='saved_at', lookup_expr='lte')
    has_notes = django_filters.BooleanFilter(method='filter_has_notes')
    
    # Property-related filters
    property_city = django_filters.CharFilter(field_name='property__city', lookup_expr='icontains')
    property_country = django_filters.CharFilter(field_name='property__country', lookup_expr='icontains')
    property_type = django_filters.ChoiceFilter(field_name='property__property_type', choices=Property.PROPERTY_TYPE_CHOICES)
    property_status = django_filters.ChoiceFilter(field_name='property__status', choices=Property.STATUS_CHOICES)
    property_price_min = django_filters.NumberFilter(field_name='property__price_per_night', lookup_expr='gte')
    property_price_max = django_filters.NumberFilter(field_name='property__price_per_night', lookup_expr='lte')
    
    class Meta:
        model = SavedProperty
        fields = ['user', 'property', 'saved_at']
    
    def filter_has_notes(self, queryset, name, value):
        """Filter saved properties with notes"""
        if value:
            return queryset.exclude(Q(notes__isnull=True) | Q(notes__exact=''))
        elif value is False:
            return queryset.filter(Q(notes__isnull=True) | Q(notes__exact=''))
        return queryset


class PropertyImageFilter(django_filters.FilterSet):
    """Filter for PropertyImage model"""
    from .models import PropertyImage
    
    property = django_filters.UUIDFilter(field_name='property__id')
    is_primary = django_filters.BooleanFilter()
    room_type = django_filters.CharFilter(lookup_expr='icontains')
    has_caption = django_filters.BooleanFilter(method='filter_has_caption')
    order_min = django_filters.NumberFilter(field_name='order', lookup_expr='gte')
    order_max = django_filters.NumberFilter(field_name='order', lookup_expr='lte')
    
    class Meta:
        model = PropertyImage
        fields = ['property', 'is_primary', 'room_type', 'order']
    
    def filter_has_caption(self, queryset, name, value):
        """Filter images with captions"""
        if value:
            return queryset.exclude(Q(caption__isnull=True) | Q(caption__exact=''))
        elif value is False:
            return queryset.filter(Q(caption__isnull=True) | Q(caption__exact=''))
        return queryset