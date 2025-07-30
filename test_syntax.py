#!/usr/bin/env python3
"""
Simple syntax test to verify views.py can be imported without errors
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pms.settings')

try:
    import django
    django.setup()
    
    # Test importing views
    print("Testing imports...")
    
    # Test basic imports
    from properties.models import Property
    print("✅ Property model imported successfully")
    
    # Test views import (this will catch syntax errors)
    from properties import views
    print("✅ Properties views imported successfully")
    
    # Test specific classes
    from properties.views import PropertyViewSet, AIPropertyExtractView
    print("✅ PropertyViewSet and AIPropertyExtractView imported successfully")
    
    print("🎉 All imports successful!")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1) 