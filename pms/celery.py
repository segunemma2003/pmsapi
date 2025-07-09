import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')

app = Celery('oifyk')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
    
    
app.conf.beat_schedule = {
    'auto-sync-ical': {
        'task': 'properties.tasks.auto_sync_all_properties',
        'schedule': crontab(minute=0),  # Run every hour
    },
    
    'send-daily-booking-reminders': {
        'task': 'bookings.tasks.send_daily_booking_reminders',
        'schedule': crontab(hour=10, minute=0),  # 10 AM daily
    },

    'sync-booking-statuses': {
        'task': 'bookings.tasks.sync_booking_status_from_beds24',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    'auto-sync-ical': {
        'task': 'properties.tasks.auto_sync_all_properties',
        'schedule': crontab(minute=0),  # Every hour
    },
    'cleanup-expired-availability-cache': {
        'task': 'bookings.tasks.cleanup_availability_cache',
        'schedule': crontab(minute=0, hour=2),  # Daily at 2 AM
    },
    'sync-pending-bookings-to-beds24': {
        'task': 'bookings.tasks.sync_pending_bookings',
        'schedule': crontab(minute='*/10'),  # Every 10 minutes
    },
    'check-booking-status-updates': {
        'task': 'bookings.tasks.sync_booking_statuses_from_beds24',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    }
}