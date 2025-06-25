from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .serializers import UserSerializer, UserRegistrationSerializer
from .tasks import create_owner_defaults

User = get_user_model()

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'admin':
            return User.objects.all().order_by('-date_joined')
        elif user.user_type == 'owner':
            # Owners can see their trusted network
            from trust_levels.models import OwnerTrustedNetwork
            trusted_user_ids = OwnerTrustedNetwork.objects.filter(
                owner=user, status='active'
            ).values_list('trusted_user_id', flat=True)
            return User.objects.filter(id__in=trusted_user_ids)
        else:
            # Users can only see themselves
            return User.objects.filter(id=user.id)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def register(self, request):
        """Register new user with invitation token"""
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.save()
        
        # If user is owner, create default trust levels and Beds24 subaccount
        if user.user_type == 'owner':
            create_owner_defaults.delay(str(user.id))
        
        return Response(
            {'message': 'User registered successfully', 'user_id': str(user.id)},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """Update current user profile"""
        serializer = self.get_serializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)