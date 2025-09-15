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
            "You are an expert AI assistant designed to extract and structure data from OCR-extracted content of Material Test Reports (MTRs). "
            "You will receive text content from an MTR document and a JSON schema. Your task is to accurately parse the provided text and populate the JSON schema with the corresponding values.\n\n"
            "Instructions:\n\n"
            "Identify Key Information: Analyze the input text to find specific data points like HeatNumber, CertificationDate, PipeManufacturerName, and various chemical and mechanical test results (e.g., YieldStrength, UltimateTensileStrength, HeatC, Product1Mn).\n\n"
            "Match and Map: Map the extracted values to the corresponding keys in the provided JSON schema.\n\n"
            "Handle Missing Data: If a specific data point is not found in the text, leave its corresponding value in the JSON as null. Do not create new keys or alter the structure.\n\n"
            "Preserve Structure: Maintain the exact JSON structure, including nested objects and arrays.\n\n"
            "Format Values:\n\n"
            "For numerical values, ensure they are represented as strings.\n\n"
            "For units, include them exactly as found in the source document.\n\n"
            "For dates, convert them to the MM/DD/YYYY format if necessary.\n\n"
            "Validate: Cross-reference the extracted values with the provided criteria (e.g., HeatCEPcmCriteria) to ensure they meet the specifications. Note any discrepancies.\n\n"
            "Chemical Equivalency (VERY IMPORTANT):\n"
            "When populating HNPipeChemicalEquivResults fields (for example: Product1CEPcm, ProductCEPcmCriteria, Product1CEIIW, ProductCEIIWCriteria, Product2CEPcm, Product2CEIIW), follow these strict rules:\n"
            "1) Match by explicit labels: Prefer values that are directly labeled in the document as 'CE (Pcm)', 'C.E. (Pcm)', 'CE Pcm', 'CEIIW', 'CE (IIW)', 'CE IIW', 'Carbon Equivalent (IIW)' or similar. If the document provides 'Product 1' / 'Product 2' or 'Pipe 1' / 'Pipe 2' labels, map the CE values to the corresponding product index (Product1 -> Product1 fields, Product2 -> Product2 fields).\n"
            "2) Nearest-label rule: If a CE value is not explicitly tied to 'Product1' or 'Product2', select the CE value that appears nearest in the text to the product/pipe identifier, table row, or the chemical composition block for that product.\n"
            "3) Do NOT swap products: Avoid assigning Product2's CE to Product1 and vice versa. If there are multiple CE values and you cannot confidently map them to a product by label or proximity, leave the ambiguous fields null.\n"
            "4) Normalization and format: Return numeric CE values as strings, preserving decimals. If the source shows a leading decimal like '.354', normalize to '0.354' for consistency. Do not add units.\n"
            "5) Criteria fields: For fields named '*Criteria' (e.g., ProductCEPcmCriteria), populate them only when the document explicitly shows a specification or criteria value. If no explicit criteria is present, leave the criteria field null.\n"
            "6) Verification: After extracting CE values, echo a short clarifying note in the JSON under an additional top-level key 'ExtractionNotes' (optional) only when you had to pick between ambiguous matches — otherwise omit this key. The primary output must remain the template structure.\n\n"
            "Tensile Results (IMPORTANT):\n"
            "When extracting tensile/mechanical test results (for example: YieldStrength, UltimateTensileStrength, YTRatio, SeamWeldTensileStrength and their unit fields), follow these strict rules:\n"
            "1) Prefer explicit labels: Look for labels such as 'Yield Strength', 'YS', 'YieldStrength', 'Yield (ksi)', 'Ultimate Tensile Strength', 'UTS', 'Seam Weld Tensile', 'Seam Weld', or similar. Map them to the corresponding fields exactly.\n"
            "2) Units: Capture units separately when they are provided (for example 'ksi'). Populate the '*Unit' field exactly as shown (e.g., 'ksi'). If a unit is missing but other values use 'ksi', infer 'ksi' only when confident; otherwise leave the unit null.\n"
            "3) YT Ratio: If a 'Y/T' or 'YTRatio' is provided (yield divided by tensile), capture the numeric string. Normalize leading decimals (e.g., '.77' -> '0.77').\n"
            "4) Numeric format: Return numeric values as strings, preserving one or two decimal places as found in the source. If the source uses a leading decimal, normalize to a leading zero ('.77' -> '0.77'). Do not append units to numeric fields — units must go into the separate '*Unit' fields.\n"
            "5) Table and proximity mapping: If results appear in a table or grouped block, map values by row/column association. Use proximity to associate a unit with its numeric value when the unit is shown once for the row.\n"
            "6) Seam weld values: Look for explicit 'Seam' or 'Seam Weld' qualifiers and map them to 'SeamWeldTensileStrength' and 'SeamWeldTensileStrengthUnits'. If only a single tensile value is present and seam weld isn't called out, do not invent seam weld entries — leave them null.\n"
            "7) Ambiguity: If more than one candidate value exists and you cannot confidently map them (by label, row, or proximity), leave the ambiguous fields null rather than guessing. Optionally include a short 'ExtractionNotes' key at top-level explaining the ambiguity.\n\n"
            "Your output must be a single, valid JSON object that adheres to the provided schema with the values replaced by the extracted data."
        )
    
    def _build_user_message(self, template: Dict[str, Any], text: str) -> str:
        """Build the user message with template and OCR text."""
        return (
            f"JSON TEMPLATE:\n{json.dumps(template, indent=2)}\n\n"
            f"OCR TEXT:\n{text[:50000]}\n\n"
            "INSTRUCTIONS (READ CAREFULLY):\n"
            "1) Output: Return ONLY a single, valid JSON object that matches the provided template structure. Do NOT output any additional text, explanation, or commentary.\n"
            "2) Use source data only: Replace template values only with data explicitly found in the OCR text. Do not invent values or use placeholder/sample values from the template.\n"
            "3) Do not change keys or structure: Preserve the exact keys, nesting, and array structure from the template. If a field cannot be found, set it to null (or empty string where appropriate per the template).\n"
            "4) Numeric formatting: All numeric fields must be returned as strings. Normalize leading decimals by adding a leading zero (e.g., '.354' -> '0.354', '.77' -> '0.77'). Preserve the number of decimals as shown in the source when possible.\n"
            "5) Units: When a unit (e.g., 'ksi') is provided in the source, populate the corresponding '*Unit' field exactly as shown. Do NOT append units to numeric fields. If a unit is not present, leave the '*Unit' field null.\n"
            "6) Dates: Convert any dates to MM/DD/YYYY format. If a date cannot be parsed confidently, leave the date field null.\n"
            "7) Chemical Equivalency mapping: For 'HNPipeChemicalEquivResults' fields (Product1CEPcm, ProductCEPcmCriteria, Product1CEIIW, ProductCEIIWCriteria, Product2CEPcm, Product2CEIIW): prefer explicitly labeled CE values (e.g., 'CE (Pcm)', 'CE Pcm', 'CEIIW', 'CE IIW'). Map values by explicit product labels first. If labels are not explicit, map by proximity to the product's chemical composition block or table row. Do NOT swap Product1 and Product2 values. If mapping is ambiguous, set the field to null.\n"
            "8) Criteria fields: Only populate '*Criteria' fields when the document explicitly lists a criteria/specification value. Otherwise leave them null.\n"
            "9) Tensile/mechanical mapping: For YieldStrength, UltimateTensileStrength, YTRatio, SeamWeldTensileStrength and their unit fields: prefer explicit labels (e.g., 'Yield Strength', 'YS', 'Ultimate Tensile Strength', 'UTS', 'Seam Weld Tensile'). Capture units separately into '*Unit' fields. Normalize numeric formats (leading zeros) and return numeric values as strings. Do not create seam-weld values if the document does not call them out.\n"
            "10) Tables and proximity: If data is in a table, respect row/column associations. Use nearest-label and table-row association to map values when explicit inline labels are missing.\n"
            "11) Ambiguity policy: If you cannot confidently map a value according to the rules above, set the field to null. Optionally include a short top-level key 'ExtractionNotes' with concise reasons when you purposely left fields null due to ambiguity (keep this note minimal).\n"
            "12) JSON validity: Ensure the returned JSON is syntactically valid (no trailing commas, correct quoting). Numeric strings should remain quoted.\n"
            "13) Final check: Before returning, ensure the object exactly matches the template keys and nesting; do not add extra metadata except the optional 'ExtractionNotes' when necessary.\n\n"
            "Return the populated JSON object now."
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
        
        # Initialize DB client if configured
        try:
            from scripts.db_client import DBClient
        except Exception:
            # local import failure should not break the processor initialization
            DBClient = None

        db_cfg = self.config.get("db", {})
        if DBClient and db_cfg.get("base_url"):
            try:
                self.db_client = DBClient(
                    base_url=db_cfg.get("base_url"),
                    org_id=db_cfg.get("org_id", ""),
                    database_name=db_cfg.get("database_name", ""),
                    login_master_id=db_cfg.get("login_master_id", ""),
                    api_key=db_cfg.get("api_key"),
                    auth_path=db_cfg.get("auth_path", "/auth/token"),
                )
                print("DB client initialized")
            except Exception as e:
                print(f"Warning: failed to initialize DB client: {e}")
                self.db_client = None
        else:
            self.db_client = None

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
        
        # Database / API integration configuration
        config["db"] = {
            "base_url": os.getenv("DB_API_BASE_URL") or os.getenv("DB_API_BASEURL") or "",
            "org_id": os.getenv("ORG_ID") or os.getenv("ORGID") or "",
            "database_name": os.getenv("DATABASE_NAME") or os.getenv("DB_NAME") or "",
            "login_master_id": os.getenv("LOGIN_MASTER_ID") or os.getenv("LOGINMASTERID") or "",
            "api_key": os.getenv("DB_API_KEY") or None,
            "auth_path": os.getenv("DB_AUTH_PATH") or "/auth/token",
        }
        
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
