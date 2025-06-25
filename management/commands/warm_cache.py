from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.contrib.auth import get_user_model
from properties.models import Property
from trust_levels.models import OwnerTrustedNetwork

User = get_user_model()

class Command(BaseCommand):
    help = 'Warm up frequently accessed cache keys'
    
    def handle(self, *args, **options):
        self.stdout.write('Warming up cache...')
        
        # Cache user profiles
        for user in User.objects.filter(status='active'):
            cache_key = f'user_profile_{user.id}'
            cache.set(cache_key, user, timeout=3600)
        
        # Cache trust network sizes
        for owner in User.objects.filter(user_type='owner', status='active'):
            network_size = OwnerTrustedNetwork.objects.filter(
                owner=owner, status='active'
            ).count()
            cache.set(f'trust_network_size_{owner.id}', network_size, timeout=300)
        
        # Cache accessible properties for users
        for user in User.objects.filter(user_type='user', status='active'):
            trusted_owners = OwnerTrustedNetwork.objects.filter(
                trusted_user=user, status='active'
            ).values_list('owner_id', flat=True)
            
            property_ids = list(Property.objects.filter(
                owner__in=trusted_owners, status='active'
            ).values_list('id', flat=True))
            
            cache.set(f'user_accessible_properties_{user.id}', property_ids, timeout=300)
        
        self.stdout.write(self.style.SUCCESS('Cache warmed successfully'))
