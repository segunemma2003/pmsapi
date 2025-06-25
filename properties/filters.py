import django_filters
from .models import Property

class PropertyFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(lookup_expr='icontains')
    state = django_filters.CharFilter(lookup_expr='icontains')
    country = django_filters.CharFilter(lookup_expr='icontains')
    price_min = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price_per_night', lookup_expr='lte')
    bedrooms_min = django_filters.NumberFilter(field_name='bedrooms', lookup_expr='gte')
    max_guests_min = django_filters.NumberFilter(field_name='max_guests', lookup_expr='gte')
    
    class Meta:
        model = Property
        fields = ['status', 'is_featured', 'owner']