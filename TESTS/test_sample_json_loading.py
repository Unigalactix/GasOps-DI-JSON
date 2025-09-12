#!/usr/bin/env python3
"""
Test Script: Sample JSON Template Loading
Tests if sample.json file is being read correctly by the main scripts.
"""

import os
import sys
import json
from pathlib import Path

def test_sample_json_loading():
    """Test loading sample.json template from various locations."""
    print("Testing Sample JSON Template Loading")
    print("=" * 50)
    
    # Test locations where sample.json might be located
    test_locations = [
        # Absolute path (hardcoded in original script)
        r"C:\Users\kodag\Downloads\GITHUB\GasOps-DI-JSON\Sample json\sample.json",
        
        # Relative path from current script location
        os.path.join(os.path.dirname(__file__), "Sample json", "sample.json"),
        
        # Alternative relative paths
        os.path.join("Sample json", "sample.json"),
        "./Sample json/sample.json",
        "Sample json/sample.json",
        
        # In case it's in the current directory
        "sample.json",
        
        # Using pathlib for cross-platform compatibility
        str(Path(__file__).parent / "Sample json" / "sample.json"),
    ]
    
    print("Checking template locations:")
    print("-" * 30)
    
    found_templates = []
    
    for i, path in enumerate(test_locations, 1):
        print(f"{i}. Testing: {path}")
        
        try:
            if os.path.exists(path):
                print(f"   ✓ File exists!")
                
                # Try to load and parse the JSON
                with open(path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                
                print(f"   ✓ Successfully loaded JSON with {len(template_data)} top-level fields")
                
                # Show some key information about the template
                if "CompanyMTRFileID" in template_data:
                    print(f"   ✓ Contains CompanyMTRFileID: {template_data['CompanyMTRFileID']}")
                
                if "HNPipeDetails" in template_data:
                    pipe_details = template_data["HNPipeDetails"]
                    if isinstance(pipe_details, list) and len(pipe_details) > 0:
                        print(f"   ✓ Contains HNPipeDetails array with {len(pipe_details)} item(s)")
                        
                        # Check for chemical results
                        first_pipe = pipe_details[0]
                        if "HNPipeHeatChemicalResults" in first_pipe:
                            chem_keys = list(first_pipe["HNPipeHeatChemicalResults"].keys())
                            print(f"   ✓ HNPipeHeatChemicalResults has {len(chem_keys)} fields")
                
                found_templates.append({
                    "path": path,
                    "data": template_data,
                    "size": len(json.dumps(template_data))
                })
                
            else:
                print(f"   ✗ File not found")
                
        except json.JSONDecodeError as e:
            print(f"   ✗ JSON parsing error: {e}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print()
    
    # Summary
    print("=" * 50)
    print(f"SUMMARY: Found {len(found_templates)} valid template(s)")
    
    if found_templates:
        print("\nValid templates found:")
        for i, template in enumerate(found_templates, 1):
            print(f"{i}. {template['path']}")
            print(f"   Size: {template['size']} characters")
            print(f"   Top-level fields: {list(template['data'].keys())}")
        
        # Return the first found template for further testing
        return found_templates[0]
    else:
        print("\n❌ No valid sample.json templates found!")
        print("\nPlease ensure sample.json exists in one of these locations:")
        for path in test_locations[:3]:  # Show main expected locations
            print(f"  - {path}")
        return None

def test_template_cleaning():
    """Test the template cleaning function from the main scripts."""
    print("\n" + "=" * 50)
    print("Testing Template Cleaning Function")
    print("=" * 50)
    
    # Load a template first
    template_info = test_sample_json_loading()
    if not template_info:
        print("Cannot test cleaning - no template found")
        return
    
    original_template = template_info["data"]
    
    print(f"Original template preview:")
    print(f"CompanyMTRFileID: {original_template.get('CompanyMTRFileID')}")
    print(f"HeatNumber: {original_template.get('HeatNumber')}")
    
    # Test the cleaning function (mimicking the one from main scripts)
    def clean_template_values(obj):
        """Clean template values for testing."""
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    cleaned[key] = clean_template_values(value)
                elif isinstance(value, str):
                    cleaned[key] = ""
                elif isinstance(value, (int, float)):
                    cleaned[key] = None
                elif isinstance(value, bool):
                    cleaned[key] = None
                else:
                    cleaned[key] = None
            return cleaned
        elif isinstance(obj, list):
            if len(obj) > 0:
                return [clean_template_values(obj[0])]
            else:
                return []
        else:
            return obj
    
    print("\nCleaning template...")
    cleaned_template = clean_template_values(original_template)
    
    print(f"Cleaned template preview:")
    print(f"CompanyMTRFileID: {cleaned_template.get('CompanyMTRFileID')}")
    print(f"HeatNumber: {cleaned_template.get('HeatNumber')}")
    
    # Show structure preservation
    print(f"\nStructure preservation check:")
    print(f"Original keys: {list(original_template.keys())}")
    print(f"Cleaned keys: {list(cleaned_template.keys())}")
    print(f"Keys match: {list(original_template.keys()) == list(cleaned_template.keys())}")
    
    return cleaned_template

def test_main_script_integration():
    """Test how the main scripts would load the template."""
    print("\n" + "=" * 50)
    print("Testing Main Script Integration")
    print("=" * 50)
    
    # Simulate the original script's load_sample_json_template function
    def load_sample_json_template_original():
        """Simulate the original function."""
        # Try absolute path first
        absolute_path = r"C:\Users\kodag\Downloads\GITHUB\GasOps-DI-JSON\Sample json\sample.json"
        
        # Try relative path as fallback
        relative_path = os.path.join(os.path.dirname(__file__), "Sample json", "sample.json")
        
        for sample_path in [absolute_path, relative_path]:
            try:
                if os.path.exists(sample_path):
                    with open(sample_path, 'r', encoding='utf-8') as f:
                        template = json.load(f)
                    print(f"✓ Original method: Loaded from {sample_path}")
                    return template, sample_path
            except Exception as e:
                print(f"✗ Original method failed for {sample_path}: {e}")
                continue
        
        print("✗ Original method: Could not load from any location")
        return None, None
    
    # Test the original method
    template, path = load_sample_json_template_original()
    
    if template:
        print(f"✓ Template successfully loaded")
        print(f"✓ Path: {path}")
        print(f"✓ Contains {len(template)} top-level fields")
        
        # Test specific fields that are important for materials testing
        important_fields = [
            "CompanyMTRFileID",
            "HeatNumber", 
            "CertificationDate",
            "MatlFacilityDetails",
            "HNPipeDetails"
        ]
        
        print("\nChecking important fields:")
        for field in important_fields:
            if field in template:
                print(f"✓ {field}: Present")
            else:
                print(f"✗ {field}: Missing")
        
        # Check nested structure
        if "HNPipeDetails" in template and isinstance(template["HNPipeDetails"], list):
            if len(template["HNPipeDetails"]) > 0:
                pipe_detail = template["HNPipeDetails"][0]
                nested_fields = [
                    "HNPipeHeatChemicalResults",
                    "HNPipeChemicalCompResults", 
                    "HNPipeTensileTestResults"
                ]
                
                print("\nChecking nested pipe detail fields:")
                for field in nested_fields:
                    if field in pipe_detail:
                        if isinstance(pipe_detail[field], dict):
                            print(f"✓ {field}: Present (dict with {len(pipe_detail[field])} fields)")
                        else:
                            print(f"✓ {field}: Present ({type(pipe_detail[field]).__name__})")
                    else:
                        print(f"✗ {field}: Missing")
        
        return True
    else:
        print("❌ Template loading failed!")
        return False

def main():
    """Run all template loading tests."""
    print("Sample JSON Template Loading Test Suite")
    print("=" * 60)
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script location: {os.path.dirname(__file__)}")
    print()
    
    # Run tests
    test_sample_json_loading()
    test_template_cleaning()
    success = test_main_script_integration()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED - Template loading works correctly!")
    else:
        print("❌ TESTS FAILED - Template loading needs attention!")
    
    print("\nTo fix template loading issues:")
    print("1. Ensure sample.json exists in the 'Sample json' folder")
    print("2. Check file permissions and encoding (should be UTF-8)")
    print("3. Validate JSON syntax using an online JSON validator")
    print("4. Update absolute paths in scripts if necessary")

if __name__ == "__main__":
    main()
