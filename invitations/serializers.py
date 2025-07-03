from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Invitation
from django.utils import timezone

User = get_user_model()

class InvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.CharField(source='invited_by.full_name', read_only=True)
    accepted_by_name = serializers.CharField(source='accepted_by.full_name', read_only=True)
    is_valid = serializers.SerializerMethodField()
    can_send_reminder = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    
    class Meta:
        model = Invitation
        fields = [
            'id', 'email', 'invitee_name', 'invitation_type', 'status',
            'personal_message', 'invited_by', 'invited_by_name', 
            'accepted_by', 'accepted_by_name', 'invitation_token',
            'expires_at', 'accepted_at', 'created_at', 'updated_at',
            'reminder_count', 'last_reminder_sent', 'is_valid',
            'can_send_reminder', 'days_until_expiry'
        ]
        read_only_fields = [
            'id', 'invited_by', 'accepted_by', 'invitation_token',
            'accepted_at', 'created_at', 'updated_at', 'reminder_count',
            'last_reminder_sent'
        ]
    
    def get_is_valid(self, obj):
        return obj.is_valid()
    
    def get_can_send_reminder(self, obj):
        return obj.can_send_reminder()
    
    def get_days_until_expiry(self, obj):
        if obj.expires_at:
            delta = obj.expires_at - timezone.now()
            return max(0, delta.days)
        return 0

class InvitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['email', 'invitee_name', 'invitation_type', 'personal_message']
    
    def validate_email(self, value):
        """Ensure no pending invitation exists for this email+type combination"""
        invitation_type = self.initial_data.get('invitation_type', 'user')
        
        existing = Invitation.objects.filter(
            email=value,
            invitation_type=invitation_type,
            status='pending',
            expires_at__gt=timezone.now()
        ).first()
        
        if existing:
            raise serializers.ValidationError(
                f"A pending {invitation_type} invitation already exists for this email. "
                f"Expires on {existing.expires_at.strftime('%Y-%m-%d')}"
            )
        
        return value
    
    def validate_invitation_type(self, value):
        """Only admins can invite owners and admins"""
        request = self.context.get('request')
        if request and request.user:
            if value in ['admin', 'owner'] and request.user.user_type != 'admin':
                raise serializers.ValidationError(
                    "Only admins can invite owners and other admins"
                )
        return value
    
    def create(self, validated_data):
        validated_data['invited_by'] = self.context['request'].user
        return super().create(validated_data)