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
    invitation_token = serializers.CharField(write_only=True, required=True)  # ← NOW REQUIRED!
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'full_name', 
            'phone', 'user_type', 'invitation_token'
        ]
        extra_kwargs = {
            'user_type': {'read_only': True}  # ← User type comes from token, not user input
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