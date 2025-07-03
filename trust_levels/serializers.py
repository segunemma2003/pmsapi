from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import TrustLevelDefinition, OwnerTrustedNetwork, TrustedNetworkInvitation

User = get_user_model()

class TrustLevelDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustLevelDefinition
        fields = [
            'id', 'level', 'name', 'description', 'default_discount_percentage',
            'color', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class OwnerTrustedNetworkSerializer(serializers.ModelSerializer):
    trusted_user_name = serializers.CharField(source='trusted_user.full_name', read_only=True)
    trusted_user_email = serializers.CharField(source='trusted_user.email', read_only=True)
    trust_level_name = serializers.SerializerMethodField()
    
    class Meta:
        model = OwnerTrustedNetwork
        fields = [
            'id', 'trusted_user', 'trusted_user_name', 'trusted_user_email',
            'trust_level', 'trust_level_name', 'discount_percentage', 'status',
            'notes', 'added_at', 'updated_at'
        ]
        read_only_fields = ['id', 'added_at', 'updated_at']
    
    def get_trust_level_name(self, obj):
        try:
            level_def = TrustLevelDefinition.objects.get(
                owner=obj.owner, level=obj.trust_level
            )
            return level_def.name
        except TrustLevelDefinition.DoesNotExist:
            return f"Level {obj.trust_level}"

class TrustedNetworkInvitationSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    trust_level_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TrustedNetworkInvitation
        fields = [
            'id', 'owner', 'owner_name', 'email', 'invitee_name', 
            'trust_level', 'trust_level_name', 'discount_percentage', 
            'personal_message', 'status', 'invitation_token', 
            'expires_at', 'accepted_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invitation_token', 'created_at', 'updated_at']
    
    def get_trust_level_name(self, obj):
        try:
            level_def = TrustLevelDefinition.objects.get(
                owner=obj.owner, level=obj.trust_level
            )
            return level_def.name
        except TrustLevelDefinition.DoesNotExist:
            return f"Level {obj.trust_level}"

class TrustedNetworkInvitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustedNetworkInvitation
        fields = ['email', 'invitee_name', 'trust_level', 'personal_message']
    
    def validate_email(self, value):
        """Check if user already in network or has pending invitation"""
        owner = self.context['request'].user
        
        # Check if user already in network
        if OwnerTrustedNetwork.objects.filter(
            owner=owner,
            trusted_user__email=value,
            status='active'
        ).exists():
            raise serializers.ValidationError(
                "User is already in your trusted network"
            )
        
        # Check for pending invitation
        if TrustedNetworkInvitation.objects.filter(
            owner=owner,
            email=value,
            status='pending'
        ).exists():
            raise serializers.ValidationError(
                "Pending invitation already exists for this email"
            )
        
        return value
    
    def validate_trust_level(self, value):
        """Validate trust level exists for owner"""
        owner = self.context['request'].user
        
        if not TrustLevelDefinition.objects.filter(
            owner=owner,
            level=value
        ).exists():
            raise serializers.ValidationError(
                "Invalid trust level for your account"
            )
        
        return value