from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache

User = get_user_model()

@shared_task(bind=True, max_retries=3)
def create_owner_defaults(self, user_id):
    """Create default trust levels for new owner (no Beds24 subaccount)"""
    try:
        user = User.objects.get(id=user_id)
        
        if user.user_type != 'owner':
            return {'success': False, 'error': 'User is not an owner'}
        
        # Create default trust levels
        from trust_levels.models import TrustLevelDefinition
        trust_levels = TrustLevelDefinition.create_default_levels(user)
        
        # Mark onboarding as completed
        user.onboarding_completed = True
        user.status = 'active'
        user.last_active_at = timezone.now()
        user.save()
        
        # Clear any cached data
        cache.delete(f'user_profile_{user_id}')
        
        return {
            'success': True, 
            'message': 'Owner defaults created successfully',
            'trust_levels_created': len(trust_levels)
        }
        
    except User.DoesNotExist:
        return {'success': False, 'error': 'User not found'}
    except Exception as e:
        if self.request.retries < self.max_retries:
            countdown = 2 ** self.request.retries * 60
            raise self.retry(countdown=countdown, exc=e)
        return {'success': False, 'error': str(e)}
