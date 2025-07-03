from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta

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
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get booking statistics"""
        timeframe = request.GET.get('timeframe', 'month')
        user = request.user
        
        # Calculate date range
        now = timezone.now()
        if timeframe == 'week':
            start_date = now - timedelta(days=7)
        elif timeframe == 'year':
            start_date = now - timedelta(days=365)
        else:  # month
            start_date = now - timedelta(days=30)
        
        # Filter bookings based on user type
        if user.user_type == 'owner':
            queryset = Booking.objects.filter(property__owner=user)
        elif user.user_type == 'admin':
            queryset = Booking.objects.all()
        else:
            queryset = Booking.objects.filter(guest=user)
        
        # Calculate statistics
        total_bookings = queryset.count()
        period_bookings = queryset.filter(created_at__gte=start_date)
        
        confirmed_bookings = queryset.filter(status='confirmed').count()
        completed_bookings = queryset.filter(status='completed').count()
        cancelled_bookings = queryset.filter(status='cancelled').count()
        
        total_revenue = queryset.filter(
            status__in=['confirmed', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        period_revenue = period_bookings.filter(
            status__in=['confirmed', 'completed']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        average_booking_value = queryset.filter(
            status__in=['confirmed', 'completed']
        ).aggregate(avg=Avg('total_amount'))['avg'] or 0
        
        # Upcoming bookings
        upcoming_bookings = queryset.filter(
            check_in_date__gte=now.date(),
            status__in=['confirmed', 'pending']
        ).count()
        
        stats = {
            'timeframe': timeframe,
            'total_bookings': total_bookings,
            'period_bookings': period_bookings.count(),
            'confirmed_bookings': confirmed_bookings,
            'completed_bookings': completed_bookings,
            'cancelled_bookings': cancelled_bookings,
            'upcoming_bookings': upcoming_bookings,
            'total_revenue': float(total_revenue),
            'period_revenue': float(period_revenue),
            'average_booking_value': float(average_booking_value),
            'confirmation_rate': (confirmed_bookings / total_bookings * 100) if total_bookings > 0 else 0,
            'cancellation_rate': (cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0,
        }
        
        # Add monthly breakdown for the period
        monthly_data = []
        current_date = start_date
        while current_date <= now:
            month_start = current_date.replace(day=1)
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            
            month_bookings = period_bookings.filter(
                created_at__gte=month_start,
                created_at__lt=next_month
            )
            
            month_revenue = month_bookings.filter(
                status__in=['confirmed', 'completed']
            ).aggregate(total=Sum('total_amount'))['total'] or 0
            
            monthly_data.append({
                'month': month_start.strftime('%Y-%m'),
                'bookings': month_bookings.count(),
                'revenue': float(month_revenue)
            })
            
            current_date = next_month
        
        stats['monthly_breakdown'] = monthly_data
        
        return Response(stats)

    @action(detail=True, methods=['get'])
    def details(self, request, pk=None):
        """Get detailed booking information"""
        booking = self.get_object()
        
        # Check permissions
        if (booking.guest != request.user and 
            booking.property.owner != request.user and 
            request.user.user_type != 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(booking)
        data = serializer.data
        
        # Add additional details
        data['nights'] = (booking.check_out_date - booking.check_in_date).days
        data['days_until_checkin'] = (booking.check_in_date - timezone.now().date()).days
        data['can_cancel'] = (
            booking.status in ['pending', 'confirmed'] and
            booking.check_in_date > timezone.now().date() + timedelta(days=1)
        )
        data['can_modify'] = (
            booking.status == 'pending' and
            booking.check_in_date > timezone.now().date() + timedelta(days=2)
        )
        
        return Response(data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking"""
        booking = self.get_object()
        
        # Check permissions
        if (booking.guest != request.user and 
            booking.property.owner != request.user and 
            request.user.user_type != 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if cancellation is allowed
        if booking.status not in ['pending', 'confirmed']:
            return Response(
                {'error': 'Booking cannot be cancelled'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check cancellation policy (24 hours before check-in)
        if booking.check_in_date <= timezone.now().date() + timedelta(days=1):
            return Response(
                {'error': 'Cannot cancel booking less than 24 hours before check-in'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cancel the booking
        booking.status = 'cancelled'
        booking.save()
        
        # Log activity
        from analytics.models import ActivityLog
        ActivityLog.objects.create(
            action='booking_cancelled',
            user=request.user,
            resource_type='booking',
            resource_id=str(booking.id),
            details={
                'booking_id': str(booking.id),
                'property_title': booking.property.title,
                'cancelled_by': request.user.user_type
            }
        )
        
        return Response({
            'message': 'Booking cancelled successfully',
            'booking_id': str(booking.id)
        })

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark booking as completed (owner only)"""
        booking = self.get_object()
        
        # Only property owner can mark as completed
        if booking.property.owner != request.user:
            return Response(
                {'error': 'Only property owner can mark booking as completed'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if booking can be completed
        if booking.status != 'confirmed':
            return Response(
                {'error': 'Only confirmed bookings can be marked as completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if check-out date has passed
        if booking.check_out_date > timezone.now().date():
            return Response(
                {'error': 'Cannot complete booking before check-out date'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Complete the booking
        booking.status = 'completed'
        booking.save()
        
        return Response({
            'message': 'Booking marked as completed',
            'booking_id': str(booking.id)
        })
