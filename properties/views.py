from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count
from django.core.cache import cache
from .models import Property, PropertyImage
from .serializers import PropertySerializer, PropertyCreateSerializer
from .filters import PropertyFilter

class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Optimized queryset with proper access control"""
        user = self.request.user
        
        # Base queryset with optimizations
        base_queryset = Property.objects.select_related('owner').annotate(
            booking_count=Count('bookings')
        ).prefetch_related('images_set')
        
        if user.user_type == 'admin':
            # Admins see all properties
            return base_queryset.all()
        elif user.user_type == 'owner':
            # Owners see their own properties
            return base_queryset.filter(owner=user)
        else:
            # Users see visible properties from owners who invited them
            cache_key = f'user_accessible_properties_{user.id}'
            property_ids = cache.get(cache_key)
            
            if property_ids is None:
                from trust_levels.models import OwnerTrustedNetwork
                trusted_owners = OwnerTrustedNetwork.objects.filter(
                    trusted_user=user,
                    status='active'
                ).values_list('owner_id', flat=True)
                
                property_ids = list(base_queryset.filter(
                    owner__in=trusted_owners,
                    status='active',
                    is_visible=True
                ).values_list('id', flat=True))
                
                cache.set(cache_key, property_ids, timeout=300)  # 5 minutes
            
            return base_queryset.filter(id__in=property_ids)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PropertyCreateSerializer
        return PropertySerializer
    
    @action(detail=True, methods=['patch'])
    def toggle_visibility(self, request, pk=None):
        """Toggle property visibility (owner only)"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only modify your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        is_visible = request.data.get('is_visible')
        if is_visible is None:
            # Toggle current visibility
            property_obj.is_visible = not property_obj.is_visible
        else:
            property_obj.is_visible = bool(is_visible)
        
        property_obj.save()
        
        # Update Beds24 visibility if synced
        if property_obj.beds24_property_id:
            from .tasks import update_beds24_visibility
            update_beds24_visibility.delay(str(property_obj.id), property_obj.is_visible)
        
        # Clear cache
        cache.delete(f'property_detail_{property_obj.id}')
        
        return Response({
            'message': f'Property visibility updated to {property_obj.is_visible}',
            'is_visible': property_obj.is_visible
        })
