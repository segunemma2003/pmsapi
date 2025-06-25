from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Prefetch
from django.core.cache import cache
from .models import Property
from .serializers import PropertySerializer, PropertyCreateSerializer
from .filters import PropertyFilter
from .tasks import submit_property_for_approval, enlist_to_beds24

class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.user_type == 'admin':
            # Admins see all properties
            return Property.objects.select_related('owner').prefetch_related(
                'bookings'
            ).all()
        elif user.user_type == 'owner':
            # Owners see their own properties
            return Property.objects.select_related('owner').prefetch_related(
                'bookings'
            ).filter(owner=user)
        else:
            # Users see properties from owners who invited them
            cache_key = f'user_accessible_properties_{user.id}'
            property_ids = cache.get(cache_key)
            
            if property_ids is None:
                from trust_levels.models import OwnerTrustedNetwork
                trusted_owners = OwnerTrustedNetwork.objects.filter(
                    trusted_user=user,
                    status='active'
                ).values_list('owner_id', flat=True)
                
                property_ids = list(Property.objects.filter(
                    owner__in=trusted_owners,
                    status='active'
                ).values_list('id', flat=True))
                
                cache.set(cache_key, property_ids, timeout=300)  # 5 minutes
            
            return Property.objects.select_related('owner').prefetch_related(
                'bookings'
            ).filter(id__in=property_ids)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PropertyCreateSerializer
        return PropertySerializer
    
    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        """Submit property for admin approval"""
        property_obj = self.get_object()
        
        if property_obj.owner != request.user:
            return Response(
                {'error': 'You can only submit your own properties'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if property_obj.status != 'draft':
            return Response(
                {'error': 'Only draft properties can be submitted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use Celery task for async processing
        submit_property_for_approval.delay(str(property_obj.id), str(request.user.id))
        
        return Response({'message': 'Property submitted for approval'})
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """Approve property (admin only)"""
        property_obj = self.get_object()
        notes = request.data.get('notes', '')
        
        property_obj.status = 'approved_pending_beds24'
        property_obj.approved_at = timezone.now()
        property_obj.approved_by = request.user
        property_obj.approval_notes = notes
        property_obj.save()
        
        return Response({'message': 'Property approved'})
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def enlist_to_beds24(self, request, pk=None):
        """Enlist property to Beds24 (admin only)"""
        property_obj = self.get_object()
        
        if property_obj.status != 'approved_pending_beds24':
            return Response(
                {'error': 'Property must be approved before enlisting to Beds24'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use Celery task for async Beds24 integration
        enlist_to_beds24.delay(str(property_obj.id), str(request.user.id))
        
        return Response({'message': 'Property enlistment to Beds24 started'})
    
    
    @action(detail=True, methods=['get'])
    def ical_export(self, request, pk=None):
        """Export property bookings as iCal"""
        property_obj = self.get_object()
        
        # Check permissions
        if not (request.user == property_obj.owner or request.user.user_type == 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get date range from query params
        start_date = request.query_params.get('start')
        end_date = request.query_params.get('end')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = datetime.now().date()
        
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = start_date + timedelta(days=365)
        
        # Generate iCal
        from beds24_integration.ical_service import ICalService
        ical_data = ICalService.generate_property_calendar(
            property_obj, start_date, end_date
        )
        
        response = HttpResponse(ical_data, content_type='text/calendar')
        response['Content-Disposition'] = f'attachment; filename="property-{property_obj.id}.ics"'
        return response
    
    @action(detail=True, methods=['post'])
    def setup_ical_sync(self, request, pk=None):
        """Setup iCal sync with Beds24"""
        property_obj = self.get_object()
        
        # Check permissions
        if not (request.user == property_obj.owner or request.user.user_type == 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not property_obj.beds24_property_id:
            return Response(
                {'error': 'Property not synced with Beds24'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get iCal settings from request
        ical_settings = {
            'icalImport': request.data.get('import_enabled', True),
            'icalExport': request.data.get('export_enabled', True),
            'icalAutoBlock': request.data.get('auto_block', True),
            'icalSyncPeriod': request.data.get('sync_interval', 24),
            'icalTimeZone': request.data.get('timezone', 'UTC')
        }
        
        # Setup iCal sync with Beds24
        from beds24_integration.services import Beds24Service
        beds24_service = Beds24Service()
        
        # Update Beds24 iCal settings
        result = beds24_service.update_property_ical_settings(
            property_obj.beds24_property_id, ical_settings
        )
        
        if result['success']:
            # Get iCal URLs
            urls_result = beds24_service.get_property_ical_urls(
                property_obj.beds24_property_id
            )
            
            if urls_result['success']:
                # Update property with iCal URLs
                property_obj.ical_import_url = urls_result['ical_urls']['import_url']
                property_obj.ical_export_url = urls_result['ical_urls']['export_url']
                property_obj.ical_sync_enabled = True
                property_obj.ical_timezone = ical_settings['icalTimeZone']
                property_obj.save()
                
                return Response({
                    'message': 'iCal sync setup successfully',
                    'ical_urls': urls_result['ical_urls']
                })
        
        return Response(
            {'error': result.get('error', 'Failed to setup iCal sync')},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'])
    def add_external_calendar(self, request, pk=None):
        """Add external iCal calendar to sync with"""
        property_obj = self.get_object()
        
        # Check permissions
        if not (request.user == property_obj.owner or request.user.user_type == 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        external_url = request.data.get('calendar_url')
        calendar_name = request.data.get('calendar_name', 'External Calendar')
        
        if not external_url:
            return Response(
                {'error': 'Calendar URL is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add to Beds24 if property is synced
        if property_obj.beds24_property_id:
            from beds24_integration.services import Beds24Service
            beds24_service = Beds24Service()
            
            result = beds24_service.import_external_ical(
                property_obj.beds24_property_id,
                external_url,
                calendar_name
            )
            
            if not result['success']:
                return Response(
                    {'error': result['error']},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Add to property's external calendars list
        external_calendars = property_obj.ical_external_calendars or []
        external_calendars.append({
            'url': external_url,
            'name': calendar_name,
            'added_at': timezone.now().isoformat(),
            'active': True
        })
        
        property_obj.ical_external_calendars = external_calendars
        property_obj.save()
        
        # Trigger sync task
        import_external_ical.delay(str(property_obj.id), external_url, calendar_name)
        
        return Response({
            'message': 'External calendar added successfully',
            'calendar_name': calendar_name
        })
    
    @action(detail=True, methods=['post'])
    def sync_ical(self, request, pk=None):
        """Trigger manual iCal sync"""
        property_obj = self.get_object()
        
        # Check permissions
        if not (request.user == property_obj.owner or request.user.user_type == 'admin'):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not property_obj.beds24_property_id:
            return Response(
                {'error': 'Property not synced with Beds24'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Trigger sync task
        sync_property_ical.delay(str(property_obj.id))
        
        return Response({
            'message': 'iCal sync started',
            'property_id': str(property_obj.id)
        })