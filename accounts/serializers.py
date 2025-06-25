from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    trust_network_size = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone', 'avatar_url',
            'user_type', 'status', 'onboarding_completed', 
            'email_verified', 'last_active_at', 'trust_network_size',
            'beds24_subaccount_id', 'date_joined'
        ]
        read_only_fields = ['id', 'beds24_subaccount_id', 'date_joined']
    
    def get_trust_network_size(self, obj):
        return obj.get_trust_network_size()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    invitation_token = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'full_name', 
            'phone', 'user_type', 'invitation_token'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        invitation_token = validated_data.pop('invitation_token', None)
        password = validated_data.pop('password')
        
        user = User.objects.create_user(
            password=password,
            username=validated_data['email'],
            **validated_data
        )
        
        # Handle invitation token if provided
        if invitation_token:
            from invitations.models import OnboardingToken, TrustedNetworkInvitation
            from invitations.tasks import process_invitation_acceptance
            process_invitation_acceptance.delay(invitation_token, str(user.id))
        
        return user