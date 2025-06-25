from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.user_type == 'admin':
            return Booking.objects.select_related(
                'property', 'guest'
            ).prefetch_related('property__owner').all().order_by('-created_at')
        elif user.user_type == 'owner':
            # Owner sees bookings for their properties
            return Booking.objects.select_related(
                'property', 'guest'
            ).filter(property__owner=user).order_by('-created_at')
        else:
            # User sees their own bookings
            return Booking.objects.select_related(
                'property'
            ).filter(guest=user).order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer
    
    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        """Update booking status"""
        booking = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in ['confirmed', 'cancelled']:
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check permissions
        if request.user.user_type not in ['admin'] and booking.property.owner != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        booking.status = new_status
        booking.save()
        
        return Response({'message': f'Booking {new_status} successfully'})
