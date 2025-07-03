from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from trust_levels.models import TrustLevelDefinition
from analytics.models import AdminAnalytics
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Setup production environment with initial data'
    
    def add_arguments(self, parser):
        parser.add_argument('--admin-email', type=str, help='Admin email address')
        parser.add_argument('--admin-password', type=str, help='Admin password')
    
    def handle(self, *args, **options):
        self.stdout.write('🚀 Setting up production environment...')
        
        with transaction.atomic():
            # Create admin user if provided
            if options['admin_email'] and options['admin_password']:
                admin_email = options['admin_email']
                admin_password = options['admin_password']
                
                if not User.objects.filter(email=admin_email).exists():
                    admin_user = User.objects.create_superuser(
                        email=admin_email,
                        username=admin_email,
                        password=admin_password,
                        user_type='admin',
                        status='active',
                        full_name='System Administrator'
                    )
                    self.stdout.write(f'✅ Created admin user: {admin_email}')
                else:
                    self.stdout.write(f'ℹ️ Admin user already exists: {admin_email}')
            
            # Initialize analytics tables
            AdminAnalytics.objects.get_or_create(
                metric_name='total_users',
                date_recorded=timezone.now().date(),
                defaults={'metric_value': 0}
            )
            
            AdminAnalytics.objects.get_or_create(
                metric_name='total_properties',
                date_recorded=timezone.now().date(),
                defaults={'metric_value': 0}
            )
            
            AdminAnalytics.objects.get_or_create(
                metric_name='total_bookings',
                date_recorded=timezone.now().date(),
                defaults={'metric_value': 0}
            )
            
            self.stdout.write('✅ Initialized analytics tables')
            
            # Warm up cache
            from utils.cache_utils import CacheManager
            CacheManager.warm_cache()
            self.stdout.write('✅ Cache warmed up')
            
            self.stdout.write('🎉 Production setup completed successfully!')