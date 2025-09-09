#!/usr/bin/env python3
"""
Object-Oriented PDF Document Intelligence Processor
Converts PDF files to JSON using Azure Document Intelligence and AI processing.
Usage: python pdf_processor_oop.py

Architecture:
- PDFProcessor: Main orchestrator class
- DocumentIntelligenceOCR: OCR extraction class  
- AITemplateProcessor: AI processing class for JSON generation
"""

import os
import sys
import json
import re
import time
import requests
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from datetime import datetime

load_dotenv()


class DocumentIntelligenceOCR:
    """Handles OCR text extraction using Azure Document Intelligence."""
    
    def __init__(self, endpoint: str, api_key: str, model_id: str = "prebuilt-document", api_version: str = "2023-07-31"):
        """Initialize OCR processor with Azure credentials."""
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.model_id = model_id
        self.api_version = api_version
        
        if not self.endpoint or not self.api_key:
            raise ValueError("Missing Azure Document Intelligence credentials")
    
    def extract_text_from_pdf(self, file_bytes: bytes, content_type: str = "application/pdf") -> str:
        """Extract text from PDF using Document Intelligence OCR."""
        print(f"Starting OCR extraction with model: {self.model_id}")
        
        # Call Document Intelligence API
        ocr_result = self._call_document_intelligence_api(file_bytes, content_type)
        
        # Extract text from result
        extracted_text = self._parse_ocr_result(ocr_result)
        
        if not extracted_text.strip():
            raise RuntimeError("No text could be extracted from the document")
        
        print(f"Successfully extracted {len(extracted_text)} characters of text")
        return extracted_text
    
    def _call_document_intelligence_api(self, file_bytes: bytes, content_type: str) -> Dict[str, Any]:
        """Make API call to Document Intelligence service."""
        analyze_url = f"{self.endpoint}/formrecognizer/documentModels/{self.model_id}:analyze?api-version={self.api_version}"
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": content_type
        }
        
        # Submit analysis request
        resp = requests.post(analyze_url, headers=headers, data=file_bytes)
        
        if resp.status_code not in (200, 202):
            self._handle_api_error(resp)
        
        # Check if we have operation location for polling
        op_location = resp.headers.get("operation-location") or resp.headers.get("Operation-Location")
        if not op_location:
            return resp.json()
        
        # Poll for completion
        return self._poll_for_completion(op_location)
    
    def _handle_api_error(self, response: requests.Response):
        """Handle API error responses with helpful hints."""
        if response.status_code == 403:
            try:
                body = response.json()
                svc_msg = body.get("error", {}).get("message", response.text)
            except Exception:
                svc_msg = response.text
            
            hint = (
                "Access denied (403). This commonly means your Document Intelligence resource has "
                "Virtual Network or Firewall restrictions. Remedies:\n"
                "1) In Azure Portal: Document Intelligence resource → Networking → Enable public access\n"
                "2) Add your client IP to the allowed IP list\n"
                "3) Configure Private Endpoint with proper DNS if using VNet"
            )
            raise RuntimeError(f"OCR API call failed: {response.status_code} {svc_msg}\n{hint}")
        
        raise RuntimeError(f"OCR API call failed: {response.status_code} {response.text}")
    
    def _poll_for_completion(self, operation_location: str, max_retries: int = 60) -> Dict[str, Any]:
        """Poll the operation location until analysis is complete."""
        print("Waiting for OCR analysis to complete...")
        
        for attempt in range(max_retries):
            time.sleep(1)
            
            get_resp = requests.get(
                operation_location, 
                headers={"Ocp-Apim-Subscription-Key": self.api_key}
            )
            
            if get_resp.status_code not in (200, 201):
                raise RuntimeError(f"Polling failed: {get_resp.status_code} {get_resp.text}")
            
            result = get_resp.json()
            status = result.get("status", "").lower()
            
            if status == "succeeded":
                print("OCR analysis completed successfully")
                return result
            elif status in ("failed", "cancelled"):
                raise RuntimeError(f"OCR analysis {status}: {result}")
        
        raise RuntimeError("Timed out waiting for OCR analysis to complete")
    
    def _parse_ocr_result(self, result_json: Dict[str, Any]) -> str:
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


class AITemplateProcessor:
    """Handles AI processing to convert OCR text into structured JSON."""
    
    def __init__(self):
        """Initialize AI processor with available credentials."""
        self.ai_config = self._detect_ai_configuration()
        if not self.ai_config:
            raise ValueError("No AI configuration found. Please configure Azure OpenAI or OpenAI credentials.")
    
    def _detect_ai_configuration(self) -> Optional[Dict[str, str]]:
        """Detect and validate available AI configuration."""
        # Check Azure OpenAI first
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_key = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        
        if azure_endpoint and azure_key and azure_deployment:
            return {
                "type": "azure_openai",
                "endpoint": azure_endpoint.rstrip('/'),
                "key": azure_key,
                "deployment": azure_deployment,
                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2023-10-01")
            }
        
        # Check OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            return {
                "type": "openai",
                "key": openai_key,
                "model": "gpt-3.5-turbo"
            }
        
        return None
    
    def load_template(self, template_path: Optional[str] = None) -> Dict[str, Any]:
        """Load and clean the JSON template."""
        if not template_path:
            # Try default locations
            template_paths = [
                r"C:\Users\kodag\Downloads\GITHUB\GasOps-DI-JSON\Sample json\sample.json",
                os.path.join(os.path.dirname(__file__), "Sample json", "sample.json")
            ]
        else:
            template_paths = [template_path]
        
        for path in template_paths:
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        template = json.load(f)
                    print(f"Loaded template from: {path}")
                    return self._clean_template_values(template)
            except Exception as e:
                print(f"Warning: Could not load template from {path}: {e}")
                continue
        
        print("Warning: Could not load template from any location, using fallback")
        return self._get_fallback_template()
    
    def _clean_template_values(self, obj: Any) -> Any:
        """Recursively clean template values, replacing sample data with null/empty values."""
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    cleaned[key] = self._clean_template_values(value)
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
                return [self._clean_template_values(obj[0])]
            else:
                return []
        else:
            return obj
    
    def _get_fallback_template(self) -> Dict[str, Any]:
        """Return a minimal fallback template structure."""
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
    
    def process_text_to_json(self, extracted_text: str, template: Dict[str, Any], timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Process extracted text into structured JSON using AI."""
        print("Processing text with AI to generate structured JSON...")
        
        system_msg = self._build_system_message()
        user_msg = self._build_user_message(template, extracted_text)
        
        try:
            response_content = self._call_ai_api(system_msg, user_msg, timeout)
            if not response_content:
                return None
            
            # Parse JSON from AI response
            parsed_json = self._extract_json_from_response(response_content)
            
            if parsed_json:
                print("Successfully generated structured JSON")
                return parsed_json
            else:
                print("Warning: Could not parse valid JSON from AI response")
                return None
                
        except Exception as e:
            print(f"AI processing failed: {e}")
            return None
    
    def _build_system_message(self) -> str:
        """Build the system message for AI processing."""
        return (
            "You are a materials science assistant that extracts data from technical documents "
            "and formats it according to a JSON template.\n"
            "Given OCR TEXT from a document and a JSON TEMPLATE, extract relevant values from the text "
            "and populate the template.\n\n"
            "Rules:\n"
            "- Only replace values in the template with data found in the OCR text\n"
            "- Keep all field names and structure exactly as in the template\n"
            "- If a value is not found in the text, set it to null for numbers, empty string for text, "
            "or empty object/array for collections\n"
            "- DO NOT use placeholder values from the template - replace them with actual data or leave null/empty\n"
            "- For chemical composition and material properties, extract exact values with units\n"
            "- Return only the populated JSON object (no surrounding explanation)\n"
            "- Ensure the output is valid JSON"
        )
    
    def _build_user_message(self, template: Dict[str, Any], text: str) -> str:
        """Build the user message with template and OCR text."""
        return (
            f"JSON TEMPLATE:\n{json.dumps(template, indent=2)}\n\n"
            f"OCR TEXT:\n{text[:50000]}\n\n"
            "Return the populated JSON template with values extracted from the OCR text. "
            "IMPORTANT: Do not use any placeholder values from the template - only use actual data "
            "found in the OCR text. If no data is found for a field, leave it null or empty."
        )
    
    def _call_ai_api(self, system_msg: str, user_msg: str, timeout: int) -> Optional[str]:
        """Make API call to the configured AI service."""
        payload = {
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0,
            "max_tokens": 4000,
        }
        
        if self.ai_config["type"] == "azure_openai":
            return self._call_azure_openai(payload, timeout)
        elif self.ai_config["type"] == "openai":
            return self._call_openai(payload, timeout)
        else:
            raise ValueError(f"Unknown AI configuration type: {self.ai_config['type']}")
    
    def _call_azure_openai(self, payload: Dict[str, Any], timeout: int) -> Optional[str]:
        """Call Azure OpenAI API."""
        url = (f"{self.ai_config['endpoint']}/openai/deployments/{self.ai_config['deployment']}/"
               f"chat/completions?api-version={self.ai_config['api_version']}")
        headers = {"api-key": self.ai_config["key"], "Content-Type": "application/json"}
        
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Azure OpenAI API call failed: {resp.status_code} {resp.text}")
        
        body = resp.json()
        return body.get("choices", [])[0].get("message", {}).get("content")
    
    def _call_openai(self, payload: Dict[str, Any], timeout: int) -> Optional[str]:
        """Call OpenAI API."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.ai_config['key']}", "Content-Type": "application/json"}
        payload["model"] = self.ai_config["model"]
        
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"OpenAI API call failed: {resp.status_code} {resp.text}")
        
        body = resp.json()
        return body.get("choices", [])[0].get("message", {}).get("content")
    
    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from AI response."""
        # Try to find JSON object first
        starts = [m.start() for m in re.finditer(r"\{", response)]
        for start in starts:
            depth = 0
            for i in range(start, len(response)):
                if response[i] == "{":
                    depth += 1
                elif response[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = response[start:i+1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            break
        
        # If no object found, try array
        starts = [m.start() for m in re.finditer(r"\[", response)]
        for start in starts:
            depth = 0
            for i in range(start, len(response)):
                if response[i] == "[":
                    depth += 1
                elif response[i] == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = response[start:i+1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            break
        
        # Fallback: try to parse the entire response
        try:
            return json.loads(response)
        except Exception:
            return None


class PDFProcessor:
    """Main orchestrator class for PDF document processing."""
    
    def __init__(self):
        """Initialize the PDF processor with OCR and AI components."""
        # Load configuration
        self.config = self._load_configuration()
        
        # Initialize components
        self.ocr_processor = DocumentIntelligenceOCR(
            endpoint=self.config["azure_di_endpoint"],
            api_key=self.config["azure_di_key"],
            model_id=self.config.get("azure_di_model_id", "prebuilt-document"),
            api_version=self.config.get("azure_di_api_version", "2023-07-31")
        )
        
        self.ai_processor = AITemplateProcessor()
        
        print("PDF Processor initialized successfully")
    
    def _load_configuration(self) -> Dict[str, str]:
        """Load and validate configuration from environment variables."""
        config = {}
        
        # Azure Document Intelligence configuration
        config["azure_di_endpoint"] = (
            os.getenv("AZURE_DI_ENDPOINT") or 
            os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
        )
        config["azure_di_key"] = (
            os.getenv("AZURE_DI_KEY") or 
            os.getenv("AZURE_FORM_RECOGNIZER_KEY")
        )
        config["azure_di_model_id"] = os.getenv("AZURE_DI_MODEL_ID", "prebuilt-document")
        config["azure_di_api_version"] = os.getenv("AZURE_DI_API_VERSION", "2023-07-31")
        
        # Validate required configuration
        if not config["azure_di_endpoint"] or not config["azure_di_key"]:
            raise ValueError(
                "Missing Azure Document Intelligence credentials. "
                "Please configure AZURE_DI_ENDPOINT and AZURE_DI_KEY in .env file."
            )
        
        return config
    
    def process_pdf(self, pdf_path: str, output_path: Optional[str] = None, template_path: Optional[str] = None) -> str:
        """
        Process a PDF file and return the output JSON file path.
        
        Args:
            pdf_path: Path to the input PDF file
            output_path: Optional custom output path for JSON file
            template_path: Optional custom template path
            
        Returns:
            Path to the generated JSON file
        """
        # Validate input file
        self._validate_pdf_file(pdf_path)
        
        print(f"Processing PDF file: {pdf_path}")
        
        # Step 1: Read PDF file
        with open(pdf_path, 'rb') as f:
            file_bytes = f.read()
        
        # Step 2: Extract text using OCR
        print("Step 1: Extracting text using Document Intelligence...")
        extracted_text = self.ocr_processor.extract_text_from_pdf(file_bytes)
        
        # Step 3: Load template
        template = self.ai_processor.load_template(template_path)
        
        # Step 4: Process with AI to generate JSON
        print("Step 2: Processing with AI to generate structured JSON...")
        generated_json = self.ai_processor.process_text_to_json(extracted_text, template)
        
        if not generated_json:
            raise RuntimeError("AI could not process the extracted text into structured JSON")
        
        # Step 5: Save output JSON
        final_output_path = self._save_json_output(pdf_path, generated_json, output_path)
        
        print(f"Successfully generated: {final_output_path}")
        return final_output_path
    
    def _validate_pdf_file(self, pdf_path: str):
        """Validate the input PDF file."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"File not found: {pdf_path}")
        
        if not pdf_path.lower().endswith('.pdf'):
            raise ValueError("Input file must be a PDF file")
    
    def _save_json_output(self, pdf_path: str, json_data: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """Save the generated JSON to file."""
        if output_path:
            final_path = output_path
        else:
            # Generate default output path
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            final_path = os.path.join(os.path.dirname(pdf_path), f"{base_name}.json")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        
        with open(final_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        return final_path
    
    def process_multiple_pdfs(self, pdf_paths: list, output_dir: Optional[str] = None) -> list:
        """
        Process multiple PDF files.
        
        Args:
            pdf_paths: List of PDF file paths
            output_dir: Optional output directory for all JSON files
            
        Returns:
            List of generated JSON file paths
        """
        results = []
        failed_files = []
        
        for i, pdf_path in enumerate(pdf_paths, 1):
            try:
                print(f"\nProcessing file {i}/{len(pdf_paths)}: {os.path.basename(pdf_path)}")
                
                output_path = None
                if output_dir:
                    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
                    output_path = os.path.join(output_dir, f"{base_name}.json")
                
                result_path = self.process_pdf(pdf_path, output_path)
                results.append(result_path)
                
            except Exception as e:
                print(f"Error processing {pdf_path}: {e}")
                failed_files.append((pdf_path, str(e)))
        
        # Summary
        print(f"\n{'='*50}")
        print(f"Batch Processing Complete!")
        print(f"✅ Successfully processed: {len(results)} files")
        if failed_files:
            print(f"❌ Failed: {len(failed_files)} files")
            for failed_path, error in failed_files:
                print(f"   - {os.path.basename(failed_path)}: {error}")
        print(f"{'='*50}")
        
        return results


def main():
    """Main entry point for the object-oriented PDF processor."""
    print("Object-Oriented PDF Document Intelligence Processor")
    print("Converts PDF files to structured JSON using AI")
    print("=" * 60)
    
    try:
        # Initialize processor
        processor = PDFProcessor()
        
        # Interactive mode
        while True:
            print("\nSelect an option:")
            print("1. Process a single PDF file")
            print("2. Process multiple PDF files")
            print("3. Exit")
            
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice == "1":
                # Single file processing
                pdf_path = input("\nEnter the path to your PDF file: ").strip()
                
                # Remove quotes if present
                if pdf_path.startswith('"') and pdf_path.endswith('"'):
                    pdf_path = pdf_path[1:-1]
                if pdf_path.startswith("'") and pdf_path.endswith("'"):
                    pdf_path = pdf_path[1:-1]
                
                if not pdf_path:
                    print("Error: Please enter a file path.")
                    continue
                
                try:
                    # Ask for custom output path
                    use_default = input("Use default output filename? (y/n) [default: y]: ").strip().lower()
                    custom_output = None
                    if use_default == 'n':
                        custom_output = input("Enter custom output path (or press Enter for default): ").strip()
                        if not custom_output:
                            custom_output = None
                    
                    print("\nStarting processing...")
                    result_path = processor.process_pdf(pdf_path, custom_output)
                    
                    print(f"\n{'='*50}")
                    print("✅ Processing Complete!")
                    print(f"📄 Input:  {pdf_path}")
                    print(f"📋 Output: {result_path}")
                    print("="*50)
                    
                except Exception as e:
                    print(f"\nError: {e}")
            
            elif choice == "2":
                # Multiple file processing
                print("\nEnter PDF file paths (one per line, empty line to finish):")
                pdf_paths = []
                while True:
                    path = input().strip()
                    if not path:
                        break
                    # Remove quotes if present
                    if path.startswith('"') and path.endswith('"'):
                        path = path[1:-1]
                    if path.startswith("'") and path.endswith("'"):
                        path = path[1:-1]
                    pdf_paths.append(path)
                
                if not pdf_paths:
                    print("No files specified.")
                    continue
                
                # Ask for output directory
                output_dir = input("\nEnter output directory (or press Enter for same directory as input): ").strip()
                if not output_dir:
                    output_dir = None
                
                try:
                    results = processor.process_multiple_pdfs(pdf_paths, output_dir)
                    print(f"\nGenerated {len(results)} JSON files")
                except Exception as e:
                    print(f"\nError during batch processing: {e}")

            elif choice == "3":
                print("\nGoodbye! 👋")
                break
            
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
