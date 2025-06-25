from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

@shared_task
def create_owner_defaults(user_id):
    """Create default trust levels and Beds24 subaccount for new owner"""
    try:
        user = User.objects.get(id=user_id)
        
        if user.user_type != 'owner':
            return {'success': False, 'error': 'User is not an owner'}
        
        # Create default trust levels
        from trust_levels.models import TrustLevelDefinition
        TrustLevelDefinition.create_default_levels(user)
        
        # Create Beds24 subaccount
        from beds24_integration.services import Beds24Service
        beds24_service = Beds24Service()
        
        try:
            result = beds24_service.create_subaccount(user)
            if result['success']:
                user.beds24_subaccount_id = result['subaccount_id']
                user.save()
        except Exception as e:
            # Log error but don't fail the entire process
            print(f"Failed to create Beds24 subaccount for user {user_id}: {str(e)}")
        
        # Mark onboarding as completed
        user.onboarding_completed = True
        user.status = 'active'
        user.last_active_at = timezone.now()
        user.save()
        
        return {'success': True, 'message': 'Owner defaults created successfully'}
        
    except User.DoesNotExist:
        return {'success': False, 'error': 'User not found'}
    except Exception as e:
        return {'success': False, 'error': str(e)}