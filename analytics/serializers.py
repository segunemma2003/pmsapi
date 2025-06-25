from rest_framework import serializers
from .models import ActivityLog, AdminAnalytics

class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'action', 'user', 'user_name', 'resource_type', 
            'resource_id', 'details', 'created_at'
        ]

class AdminAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminAnalytics
        fields = '__all__'