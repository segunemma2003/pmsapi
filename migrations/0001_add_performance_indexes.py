from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0001_initial'),
        ('properties', '0001_initial'),
        ('bookings', '0001_initial'),
        ('trust_levels', '0001_initial'),
    ]

    operations = [
        # Add composite indexes for common queries
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_owner_status ON properties (owner_id, status);"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_property_status ON bookings (property_id, status);"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bookings_guest_status ON bookings (guest_id, status);"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trust_networks_owner_status ON owner_trusted_networks (owner_id, status);"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trust_networks_user_status ON owner_trusted_networks (trusted_user_id, status);"
        ),
        
        # Add partial indexes for active records
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_active ON properties (created_at) WHERE status = 'active';"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_active ON users (created_at) WHERE status = 'active';"
        ),
        
        # Add indexes for search functionality
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_search ON properties USING gin(to_tsvector('english', title || ' ' || description));"
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_properties_location ON properties (city, state, country) WHERE status = 'active';"
        ),
    ]