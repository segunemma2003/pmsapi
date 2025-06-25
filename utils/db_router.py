from django.conf import settings


class DatabaseRouter:
    """
    Route reads to replica and writes to primary database
    """
    def db_for_read(self, model, **hints):
        """Reading from the replica database when available"""
        if hasattr(settings, 'DATABASES') and 'replica' in settings.DATABASES:
            return 'replica'
        return 'default'

    def db_for_write(self, model, **hints):
        """Writing to the primary database"""
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        """Relations between objects are allowed"""
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """All migrations go to primary"""
        return db == 'default'
