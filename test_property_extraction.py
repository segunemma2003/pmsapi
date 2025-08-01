#!/usr/bin/env python3

# Simple test for property type extraction
import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from properties.nlp_utils import NLPProcessor
    
    # Test cases
    test_cases = [
        "I have a house",
        "It's a house",
        "house",
        "My property is a house",
        "This is a house for rent",
        "apartment",
        "I have an apartment",
        "villa for listing"
    ]
    
    processor = NLPProcessor()
    
    print("Testing property type extraction:")
    print("=" * 50)
    
    for test_text in test_cases:
        print(f"\nTesting: '{test_text}'")
        result = processor.extract_property_data(test_text)
        extracted_data = result.get('extracted_data', {})
        property_type = extracted_data.get('property_type')
        print(f"Extracted property_type: {property_type}")
        
    print("\n" + "=" * 50)
    print("Test completed!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc() 