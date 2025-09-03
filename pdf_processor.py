#!/usr/bin/env python3
"""
PDF Document Intelligence Processor
Converts PDF files to JSON using Azure Document Intelligence and AI processing.
Usage: python pdf_processor.py
"""

import os
import sys
import json
import re
import time
import requests
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime

load_dotenv()

# AI helpers (Azure OpenAI or OpenAI)
def _has_azure_openai():
    endpoint = get_config_value("AZURE_OPENAI_ENDPOINT")
    key = get_config_value("AZURE_OPENAI_KEY") or get_config_value("AZURE_OPENAI_API_KEY")
    deployment = get_config_value("AZURE_OPENAI_DEPLOYMENT")
    return bool(endpoint and key and deployment)

def _has_openai_key():
    return bool(get_config_value("OPENAI_API_KEY"))

# Configuration from .env
def get_config_value(key: str, default: str = None):
    """Get configuration value from environment variables."""
    return os.getenv(key, default)

ENDPOINT = get_config_value("AZURE_DI_ENDPOINT") or get_config_value("AZURE_FORM_RECOGNIZER_ENDPOINT")
API_KEY = get_config_value("AZURE_DI_KEY") or get_config_value("AZURE_FORM_RECOGNIZER_KEY")
# Use read model for OCR only as specified
MODEL_ID = "prebuilt-read"
API_VERSION = get_config_value("AZURE_DI_API_VERSION", "2023-07-31")

def call_document_intelligence_ocr(file_bytes: bytes, content_type: str = "application/octet-stream"):
    """Call Document Intelligence read model to extract text from document."""
    if not ENDPOINT or not API_KEY:
        raise RuntimeError("Missing Azure Document Intelligence credentials. Please configure AZURE_DI_ENDPOINT and AZURE_DI_KEY in .env file.")

    analyze_url = f"{ENDPOINT.rstrip('/')}/formrecognizer/documentModels/{MODEL_ID}:analyze?api-version={API_VERSION}"
    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY,
        "Content-Type": content_type
    }

    print(f"Calling Document Intelligence with model: {MODEL_ID}")
    resp = requests.post(analyze_url, headers=headers, data=file_bytes)
    if resp.status_code not in (200, 202):
        if resp.status_code == 403:
            try:
                body = resp.json()
                svc_msg = body.get("error", {}).get("message", resp.text)
            except Exception:
                svc_msg = resp.text
            
            hint = (
                "Access denied (403). This commonly means your Document Intelligence resource has Virtual Network or Firewall restrictions. "
                "Remedies: 1) In the Azure Portal open your Document Intelligence / Cognitive Services resource → Networking, and either enable public access or add your client IP to the allowed IP list; "
                "2) If the resource is configured for private endpoint access, run the app from a VM/Function inside the same VNet or configure a Private Endpoint with proper DNS; "
                "3) For quick testing, add your current public IP to the allowed list (there's an 'Add client IP' button in the portal)."
            )
            raise RuntimeError(f"Analyze request failed: {resp.status_code} {svc_msg}\n{hint}")
        raise RuntimeError(f"Analyze request failed: {resp.status_code} {resp.text}")

    # Operation location is in headers
    op_location = resp.headers.get("operation-location") or resp.headers.get("Operation-Location")
    if not op_location:
        # Some endpoints return body directly
        return resp.json()

    # Poll for completion
    print("Waiting for analysis to complete...")
    for _ in range(60):
        time.sleep(1)
        get_resp = requests.get(op_location, headers={"Ocp-Apim-Subscription-Key": API_KEY})
        if get_resp.status_code not in (200, 201):
            raise RuntimeError(f"Polling failed: {get_resp.status_code} {get_resp.text}")
        j = get_resp.json()
        status = j.get("status")
        if status and status.lower() == "succeeded":
            return j
        if status and status.lower() in ("failed", "cancelled"):
            raise RuntimeError(f"Analysis {status}: {j}")
    raise RuntimeError("Timed out waiting for analysis to complete")

def extract_text_from_ocr_result(result_json: dict) -> str:
    """Extract plain text from Document Intelligence OCR result."""
    text_parts = []
    
    def recurse_text(obj):
        if isinstance(obj, dict):
            # Check for text content in various fields
            for key in ("content", "text", "value"):
                if key in obj and isinstance(obj[key], str):
                    text_parts.append(obj[key])
            # Recurse through other keys
            for v in obj.values():
                recurse_text(v)
        elif isinstance(obj, list):
            for item in obj:
                recurse_text(item)
    
    recurse_text(result_json)
    return "\n".join(text_parts)

def find_json_in_text(s: str):
    """Find the first balanced JSON object or array in a string and parse it."""
    
    # Try to find JSON object first
    starts = [m.start() for m in re.finditer(r"\{", s)]
    for start in starts:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start:i+1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    
    # If no object found, try array
    starts = [m.start() for m in re.finditer(r"\[", s)]
    for start in starts:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    candidate = s[start:i+1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    return None

def process_with_ai(text: str, timeout: int = 30) -> Optional[dict]:
    """Use AI to extract and structure data from OCR text based on sample.json template."""
    
    # Load sample.json as template
    sample_template = load_sample_json_template()
    
    system_msg = (
        "You are a materials science assistant that extracts data from technical documents and formats it according to a JSON template.\n"
        "Given the OCR TEXT from a document and a JSON TEMPLATE, extract relevant values from the text and populate the template.\n"
        "Rules:\n"
        "- Only replace values in the template with data found in the OCR text\n"
        "- Keep all field names and structure exactly as in the template\n"
        "- If a value is not found in the text, set it to null for numbers, empty string for text, or empty object/array for collections\n"
        "- DO NOT use placeholder values from the template - replace them with actual data or leave null/empty\n"
        "- For chemical composition and material properties, extract exact values with units\n"
        "- Return only the populated JSON object (no surrounding explanation)\n"
        "- Ensure the output is valid JSON"
    )

    user_msg = f"JSON TEMPLATE:\n{json.dumps(sample_template, indent=2)}\n\nOCR TEXT:\n{text[:50000]}\n\nReturn the populated JSON template with values extracted from the OCR text. IMPORTANT: Do not use any placeholder values from the template - only use actual data found in the OCR text. If no data is found for a field, leave it null or empty."

    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": 4000,
    }

    try:
        if _has_azure_openai():
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT").rstrip('/')
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2023-10-01")
            url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
            key = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
            headers = {"api-key": key, "Content-Type": "application/json"}
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"AI call failed: {resp.status_code} {resp.text}")
            body = resp.json()
            content = body.get("choices", [])[0].get("message", {}).get("content")
        elif _has_openai_key():
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}", "Content-Type": "application/json"}
            payload["model"] = "gpt-3.5-turbo"  # Add model for OpenAI API
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"AI call failed: {resp.status_code} {resp.text}")
            body = resp.json()
            content = body.get("choices", [])[0].get("message", {}).get("content")
        else:
            raise RuntimeError("No AI configuration found. Please configure either AZURE_OPENAI_* or OPENAI_API_KEY in .env file.")

        if not content:
            return None

        # Try to find JSON object in the response
        parsed = find_json_in_text(content)
        if not parsed:
            try:
                parsed = json.loads(content)
            except:
                return None
        
        return parsed
    except Exception as e:
        print(f"AI processing failed: {e}")
        return None

def load_sample_json_template():
    """Load the sample JSON template structure."""
    # Try absolute path first
    absolute_path = r"C:\Users\kodag\Downloads\GITHUB\GasOps-DI-JSON\Sample json\sample.json"
    
    # Try relative path as fallback
    relative_path = os.path.join(os.path.dirname(__file__), "Sample json", "sample.json")
    
    for sample_path in [absolute_path, relative_path]:
        try:
            if os.path.exists(sample_path):
                with open(sample_path, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                print(f"Loaded sample.json template from: {sample_path}")
                # Clean the template by replacing values with null/empty equivalents
                cleaned_template = clean_template_values(template)
                return cleaned_template
        except Exception as e:
            print(f"Warning: Could not load sample.json from {sample_path}: {e}")
            continue
    
    print("Warning: Could not load sample.json template from any location")
    # Fallback minimal template with null/empty values
    return {
        "CompanyMTRFileID": None,
        "HeatNumber": "",
        "ZNumber": "",
        "CertificationDate": "",
        "HNPipeDetails": [{
            "PipeNumber": "",
            "Grade": "",
            "HNPipeHeatChemicalResults": {},
            "HNPipeChemicalCompResults": {},
            "HNPipeTensileTestResults": {},
            "HNPipeCVNResults": {},
            "HNPipeHardnessResults": {}
        }]
    }

def clean_template_values(obj):
    """Recursively clean template values, replacing sample data with null/empty values."""
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
            # Keep the structure but clean the first item as a template
            return [clean_template_values(obj[0])]
        else:
            return []
    else:
        return obj

def process_pdf_file(pdf_path: str) -> str:
    """Process a PDF file and return the output JSON file path."""
    
    # Validate input file
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")
    
    if not pdf_path.lower().endswith('.pdf'):
        raise ValueError("Input file must be a PDF file")
    
    print(f"Processing PDF file: {pdf_path}")
    
    # Read PDF file
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
    
    print("Step 1: Extracting text using Document Intelligence...")
    # Step 1: Extract text using Document Intelligence
    ocr_result = call_document_intelligence_ocr(file_bytes, content_type="application/pdf")
    
    # Step 2: Extract text from result
    extracted_text = extract_text_from_ocr_result(ocr_result)
    if not extracted_text.strip():
        raise RuntimeError("No text could be extracted from the document")
    
    print(f"Extracted {len(extracted_text)} characters of text")
    print("Step 2: Processing with AI to generate structured JSON...")
    
    # Step 3: Process with AI to generate JSON
    generated_json = process_with_ai(extracted_text)
    if not generated_json:
        raise RuntimeError("AI could not process the extracted text into structured JSON")
    
    # Step 4: Save output JSON
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(os.path.dirname(pdf_path), f"{base_name}.json")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(generated_json, f, indent=2, ensure_ascii=False)
    
    print(f"Successfully generated: {output_path}")
    return output_path

def get_pdf_file_input():
    """Get PDF file path from user input with validation."""
    while True:
        print("\nPDF Document Intelligence Processor")
        print("=" * 40)
        pdf_path = input("Enter the path to your PDF file: ").strip()
        
        # Remove quotes if user wrapped the path in quotes
        if pdf_path.startswith('"') and pdf_path.endswith('"'):
            pdf_path = pdf_path[1:-1]
        if pdf_path.startswith("'") and pdf_path.endswith("'"):
            pdf_path = pdf_path[1:-1]
        
        if not pdf_path:
            print("Error: Please enter a file path.")
            continue
            
        if not os.path.exists(pdf_path):
            print(f"Error: File not found: {pdf_path}")
            retry = input("Would you like to try again? (y/n): ").strip().lower()
            if retry != 'y':
                return None
            continue
            
        if not pdf_path.lower().endswith('.pdf'):
            print("Error: File must be a PDF file.")
            retry = input("Would you like to try again? (y/n): ").strip().lower()
            if retry != 'y':
                return None
            continue
            
        return pdf_path

def main():
    """Main entry point for the application."""
    print("PDF Document Intelligence Processor")
    print("Converts PDF files to structured JSON using AI")
    print("=" * 50)
    
    try:
        # Check credentials first
        if not ENDPOINT or not API_KEY:
            print("\nError: Missing Azure Document Intelligence credentials")
            print("Please configure the following in your .env file:")
            print("AZURE_DI_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com/")
            print("AZURE_DI_KEY=your_32_character_api_key_here")
            input("\nPress Enter to exit...")
            sys.exit(1)
        
        if not (_has_azure_openai() or _has_openai_key()):
            print("\nError: Missing AI credentials")
            print("Please configure either Azure OpenAI or OpenAI credentials in your .env file:")
            print("For Azure OpenAI:")
            print("AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/")
            print("AZURE_OPENAI_KEY=your_openai_key")
            print("AZURE_OPENAI_DEPLOYMENT=your_deployment_name")
            print("For OpenAI:")
            print("OPENAI_API_KEY=your_openai_api_key")
            input("\nPress Enter to exit...")
            sys.exit(1)
        
        # Get PDF file from user input
        pdf_file = get_pdf_file_input()
        if not pdf_file:
            print("\nExiting...")
            sys.exit(0)
        
        print(f"\nSelected file: {pdf_file}")
        
        # Ask for custom output path (optional)
        output_choice = input("\nUse default output filename? (y/n) [default: y]: ").strip().lower()
        custom_output = None
        if output_choice == 'n':
            custom_output = input("Enter custom output path (or press Enter for default): ").strip()
            if not custom_output:
                custom_output = None
        
        print("\nStarting processing...")
        
        # Process the PDF file
        output_path = process_pdf_file(pdf_file)
        
        # If custom output path specified, move the file
        if custom_output:
            import shutil
            try:
                shutil.move(output_path, custom_output)
                output_path = custom_output
                print(f"Output saved to custom location: {output_path}")
            except Exception as e:
                print(f"Warning: Could not move to custom location ({e}), using default: {output_path}")
        
        print(f"\n" + "=" * 50)
        print("✅ Processing Complete!")
        print(f"📄 Input:  {pdf_file}")
        print(f"📋 Output: {output_path}")
        print("=" * 50)
        
        # Ask if user wants to process another file
        while True:
            another = input("\nProcess another PDF file? (y/n): ").strip().lower()
            if another == 'y':
                main()  # Restart the process
                return
            elif another == 'n':
                print("\nGoodbye! 👋")
                break
            else:
                print("Please enter 'y' for yes or 'n' for no.")
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()
