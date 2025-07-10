from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

User = get_user_model()

class TrustConnectionSerializer(serializers.Serializer):
    """Serializer for trust network connections"""
    owner_id = serializers.CharField(source='owner__id')
    owner_name = serializers.CharField(source='owner__full_name')
    owner_email = serializers.CharField(source='owner__email')
    trust_level = serializers.IntegerField()
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    connected_since = serializers.DateTimeField(source='added_at')

class UserSerializer(serializers.ModelSerializer):
    trust_network_size = serializers.SerializerMethodField()
    trust_connections = serializers.SerializerMethodField()
    effective_role = serializers.SerializerMethodField()
    can_switch_role = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'phone', 'avatar_url',
            'user_type', 'current_role', 'effective_role', 'about_me',
            'status', 'onboarding_completed', 'email_verified', 
            'last_active_at', 'trust_network_size', 'trust_connections',
            'beds24_subaccount_id', 'date_joined', 'can_switch_role'
        ]
        read_only_fields = ['id', 'beds24_subaccount_id', 'date_joined', 
                           'effective_role', 'trust_connections', 'can_switch_role']
    
    def get_trust_network_size(self, obj):
        return obj.get_trust_network_size()
    
    def get_trust_connections(self, obj):
        """Get all trust network connections for this user"""
        connections = obj.get_trust_connections()
        return TrustConnectionSerializer(connections, many=True).data
    
    def get_effective_role(self, obj):
        return obj.get_effective_role()
    
    def get_can_switch_role(self, obj):
        return obj.can_switch_role()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    invitation_token = serializers.CharField(write_only=True, required=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'full_name', 
            'phone', 'user_type', 'invitation_token', 'about_me'
        ]
        extra_kwargs = {
            'user_type': {'read_only': True}  # User type comes from token
        }
    
    def validate_invitation_token(self, value):
        """Validate that invitation token exists and is valid"""
        from invitations.models import OnboardingToken
        
        try:
            token_obj = OnboardingToken.objects.select_related('invitation').get(
                token=value
            )
            
            # Check if token is valid
            now = timezone.now()
            if token_obj.expires_at <= now:
                raise serializers.ValidationError("Invitation token has expired")
            
            if token_obj.used_at is not None:
                raise serializers.ValidationError("Invitation token has already been used")
            
            # Store token object for use in create()
            self._token_obj = token_obj
            return value
            
        except OnboardingToken.DoesNotExist:
            raise serializers.ValidationError("Invalid invitation token")
    
    def validate(self, attrs):
        # Check password match
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        
        # Validate email matches token email
        if hasattr(self, '_token_obj'):
            if attrs['email'].lower() != self._token_obj.email.lower():
                raise serializers.ValidationError(
                    "Email must match the invitation email address"
                )
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        invitation_token = validated_data.pop('invitation_token')
        password = validated_data.pop('password')
        
        # Get user type from token, not from user input
        token_obj = self._token_obj
        validated_data['user_type'] = token_obj.user_type
        validated_data['current_role'] = token_obj.user_type  # Set initial current role
        validated_data['status'] = 'pending'  # Will be activated after token processing
        
        # Create user
        user = User.objects.create_user(
            password=password,
            username=validated_data['email'],
            **validated_data
        )
        
        # Process invitation token
        from invitations.tasks import process_invitation_acceptance
        result = process_invitation_acceptance.delay(invitation_token, str(user.id))
        
        return user

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile including avatar"""
    class Meta:
        model = User
        fields = ['full_name', 'phone', 'about_me', 'avatar_url']
    
    def validate_avatar_url(self, value):
        """Validate avatar URL is from our upload service"""
        if value and not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError("Invalid avatar URL")
        return value

class RoleSwitchSerializer(serializers.Serializer):
    """Serializer for role switching"""
    new_role = serializers.ChoiceField(choices=['owner', 'user'])
    
    def validate(self, attrs):
        user = self.context['request'].user
        if not user.can_switch_role():
            raise serializers.ValidationError(
                "You don't have permission to switch roles"
            )
        return attrs