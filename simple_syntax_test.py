#!/usr/bin/env python3
"""
Simple syntax test that doesn't require Django setup
"""

import sys
import os

def test_syntax():
    """Test basic Python syntax without Django dependencies"""
    
    # Test files to check
    test_files = [
        'properties/views.py',
        'properties/models.py', 
        'properties/serializers.py',
        'properties/openai_views.py'
    ]
    
    print("🔍 Testing Python syntax...")
    
    for file_path in test_files:
        if os.path.exists(file_path):
            try:
                # Use py_compile to check syntax
                import py_compile
                py_compile.compile(file_path, doraise=True)
                print(f"✅ {file_path} - Syntax OK")
            except Exception as e:
                print(f"❌ {file_path} - Syntax Error: {e}")
                return False
        else:
            print(f"⚠️  {file_path} - File not found")
    
    print("🎉 All syntax tests passed!")
    return True

if __name__ == "__main__":
    success = test_syntax()
    sys.exit(0 if success else 1) 