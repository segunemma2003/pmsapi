from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class OwnerRateThrottle(UserRateThrottle):
    scope = 'owner'
    rate = '2000/hour'  # Higher rate for owners

class AdminRateThrottle(UserRateThrottle):
    scope = 'admin'
    rate = '5000/hour'  # Highest rate for admins

class PropertyCreationThrottle(UserRateThrottle):
    scope = 'property_creation'
    rate = '10/hour'  # Limit property creation

class InvitationThrottle(UserRateThrottle):
    scope = 'invitation'
    rate = '50/hour'  # Limit invitation sending