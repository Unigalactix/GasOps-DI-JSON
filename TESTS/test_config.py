#!/usr/bin/env python3
"""
Test script to verify PDF processor configuration and dependencies.
"""

import os
import sys
from dotenv import load_dotenv

def test_configuration():
    """Test if all required configurations are present."""
    load_dotenv()
    
    print("Testing PDF Processor Configuration")
    print("=" * 40)
    
    # Test Azure Document Intelligence
    print("\n1. Azure Document Intelligence:")
    endpoint = os.getenv("AZURE_DI_ENDPOINT") or os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
    api_key = os.getenv("AZURE_DI_KEY") or os.getenv("AZURE_FORM_RECOGNIZER_KEY")
    
    if endpoint and api_key:
        print(f"   ✓ Endpoint: {endpoint}")
        print(f"   ✓ API Key: {'*' * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else 'Set'}")
    else:
        print("   ✗ Missing Azure Document Intelligence credentials")
        print("   Configure AZURE_DI_ENDPOINT and AZURE_DI_KEY in .env file")
    
    # Test AI Configuration
    print("\n2. AI Configuration:")
    
    # Check Azure OpenAI
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_key = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    
    if azure_endpoint and azure_key and azure_deployment:
        print("   ✓ Azure OpenAI configured")
        print(f"   ✓ Endpoint: {azure_endpoint}")
        print(f"   ✓ Deployment: {azure_deployment}")
    else:
        # Check OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            print("   ✓ OpenAI configured")
            print(f"   ✓ API Key: {'*' * (len(openai_key) - 4) + openai_key[-4:] if len(openai_key) > 4 else 'Set'}")
        else:
            print("   ✗ No AI configuration found")
            print("   Configure either Azure OpenAI or OpenAI credentials in .env file")
    
    # Test sample.json template
    print("\n3. Sample JSON Template:")
    try:
        # Try absolute path first
        absolute_path = r"C:\Users\kodag\Downloads\GITHUB\GasOps-DI-JSON\Sample json\sample.json"
        relative_path = os.path.join(os.path.dirname(__file__), "Sample json", "sample.json")
        
        sample_path = None
        for path in [absolute_path, relative_path]:
            if os.path.exists(path):
                sample_path = path
                break
        
        if sample_path:
            import json
            with open(sample_path, 'r', encoding='utf-8') as f:
                template = json.load(f)
            print(f"   ✓ Template found with {len(template)} top-level fields")
            print(f"   ✓ Path: {sample_path}")
        else:
            print(f"   ✗ Template not found at expected locations")
    except Exception as e:
        print(f"   ✗ Error loading template: {e}")
    
    # Test dependencies
    print("\n4. Dependencies:")
    dependencies = [("requests", "requests"), ("python-dotenv", "dotenv"), ("openai", "openai")]
    all_ok = True
    
    for dep_name, import_name in dependencies:
        try:
            __import__(import_name)
            print(f"   ✓ {dep_name}")
        except ImportError:
            print(f"   ✗ {dep_name} not installed")
            all_ok = False
    
    # Final status
    print("\n" + "=" * 40)
    if endpoint and api_key and (azure_endpoint or openai_key) and sample_path and all_ok:
        print("✓ Configuration complete! Ready to process PDF files.")
        print("\nTo start the interactive processor:")
        print("python pdf_processor.py")
        print("\nOr see the demo:")
        print("python demo.py")
    else:
        print("✗ Configuration incomplete. Please fix the issues above.")
        return False
    
    return True

if __name__ == "__main__":
    test_configuration()
