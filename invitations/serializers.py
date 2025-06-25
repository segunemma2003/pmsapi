from rest_framework import serializers
from .models import Invitation, OnboardingToken
from trust_levels.models import TrustedNetworkInvitation

class InvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.CharField(source='invited_by.full_name', read_only=True)
    accepted_by_name = serializers.CharField(source='accepted_by.full_name', read_only=True)
    
    class Meta:
        model = Invitation
        fields = [
            'id', 'email', 'invitee_name', 'invitation_type', 'status',
            'personal_message', 'invited_by', 'invited_by_name', 
            'accepted_by', 'accepted_by_name', 'invitation_token',
            'expires_at', 'accepted_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'invited_by', 'accepted_by', 'invitation_token',
            'accepted_at', 'created_at', 'updated_at'
        ]

class InvitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['email', 'invitee_name', 'invitation_type', 'personal_message']
    
    def create(self, validated_data):
        validated_data['invited_by'] = self.context['request'].user
        return super().create(validated_data)

class TrustedNetworkInvitationSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    trust_level_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TrustedNetworkInvitation
        fields = [
            'id', 'email', 'invitee_name', 'trust_level', 'trust_level_name',
            'discount_percentage', 'personal_message', 'status', 'owner',
            'owner_name', 'invitation_token', 'expires_at', 'accepted_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'owner', 'invitation_token', 'status', 'accepted_at',
            'created_at', 'updated_at'
        ]
    
    def get_trust_level_name(self, obj):
        from trust_levels.models import TrustLevelDefinition
        try:
            level = TrustLevelDefinition.objects.get(
                owner=obj.owner, level=obj.trust_level
            )
            return level.name
        except TrustLevelDefinition.DoesNotExist:
            return f"Level {obj.trust_level}"

class OnboardingTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnboardingToken
        fields = [
            'token', 'email', 'user_type', 'expires_at', 'used_at', 'metadata'
        ]
        read_only_fields = ['token', 'used_at']