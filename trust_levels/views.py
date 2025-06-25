from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.cache import cache
from .models import TrustLevelDefinition, OwnerTrustedNetwork, TrustedNetworkInvitation
from .serializers import (
    TrustLevelDefinitionSerializer, OwnerTrustedNetworkSerializer,
    TrustedNetworkInvitationSerializer
)

class TrustLevelDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = TrustLevelDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return TrustLevelDefinition.objects.filter(owner=user).order_by('level')
        return TrustLevelDefinition.objects.none()
    
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class OwnerTrustedNetworkViewSet(viewsets.ModelViewSet):
    serializer_class = OwnerTrustedNetworkSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'owner':
            return OwnerTrustedNetwork.objects.select_related(
                'trusted_user'
            ).filter(owner=user, status='active').order_by('-trust_level', 'trusted_user__full_name')
        return OwnerTrustedNetwork.objects.none()
    
    @action(detail=True, methods=['patch'])
    def update_trust_level(self, request, pk=None):
        """Update user's trust level"""
        network = self.get_object()
        new_level = request.data.get('trust_level')
        notes = request.data.get('notes', '')
        
        if not new_level or not (1 <= int(new_level) <= 5):
            return Response(
                {'error': 'Valid trust level (1-5) required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get discount percentage from trust level definition
        try:
            trust_def = TrustLevelDefinition.objects.get(
                owner=request.user, level=new_level
            )
            network.trust_level = new_level
            network.discount_percentage = trust_def.default_discount_percentage
            network.notes = notes
            network.save()
            
            # Clear caches
            cache.delete(f'trust_discount_{request.user.id}_{network.trusted_user.id}')
            
            return Response({'message': 'Trust level updated successfully'})
            
        except TrustLevelDefinition.DoesNotExist:
            return Response(
                {'error': 'Trust level definition not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['delete'])
    def remove_from_network(self, request, pk=None):
        """Remove user from trusted network"""
        network = self.get_object()
        network.status = 'removed'
        network.save()
        
        # Clear caches
        cache.delete(f'trust_network_size_{request.user.id}')
        cache.delete(f'trust_discount_{request.user.id}_{network.trusted_user.id}')
        cache.delete(f'user_accessible_properties_{network.trusted_user.id}')
        
        return Response({'message': 'User removed from network'})