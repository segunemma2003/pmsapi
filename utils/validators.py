from django.core.exceptions import ValidationError
from django.core.validators import validate_email
import re

class CustomValidators:
    """Custom validation utilities"""
    
    @staticmethod
    def validate_phone_number(phone):
        """Validate phone number format"""
        if not phone:
            return True  # Optional field
        
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        
        # Check if it's a valid length (10-15 digits)
        if len(digits_only) < 10 or len(digits_only) > 15:
            raise ValidationError('Phone number must be 10-15 digits long')
        
        return True
    
    @staticmethod
    def validate_password_strength(password):
        """Validate password strength"""
        if len(password) < 8:
            raise ValidationError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', password):
            raise ValidationError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', password):
            raise ValidationError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', password):
            raise ValidationError('Password must contain at least one number')
        
        return True
    
    @staticmethod
    def validate_discount_percentage(percentage):
        """Validate discount percentage"""
        if percentage < 0 or percentage > 100:
            raise ValidationError('Discount percentage must be between 0 and 100')
        
        return True
    
    @staticmethod
    def validate_trust_level(level):
        """Validate trust level"""
        if level < 1 or level > 5:
            raise ValidationError('Trust level must be between 1 and 5')
        
        return True
