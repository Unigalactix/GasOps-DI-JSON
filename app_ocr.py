import os
import io
import json
import re
import time
import requests
import streamlit as st
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime

load_dotenv()

# AI helpers (Azure OpenAI or OpenAI) - Define functions first
def _has_azure_openai():
    return bool(os.getenv("AZURE_OPENAI_ENDPOINT") and (os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")) and os.getenv("AZURE_OPENAI_DEPLOYMENT"))

def _has_openai_key():
    return bool(os.getenv("OPENAI_API_KEY"))

# Configuration from .env
ENDPOINT = os.getenv("AZURE_DI_ENDPOINT") or os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
API_KEY = os.getenv("AZURE_DI_KEY") or os.getenv("AZURE_FORM_RECOGNIZER_KEY")
# Use layout model for OCR and table extraction
MODEL_ID = os.getenv("AZURE_DI_MODEL_ID", "prebuilt-layout")
API_VERSION = os.getenv("AZURE_DI_API_VERSION", "2023-07-31")

st.set_page_config(page_title="OCR → Material Properties Extractor", layout="wide")

st.title("Smart Document Analyzer → Material & Chemical Properties Extractor")

# Model selection UI in main area
st.subheader("Configuration")
col1, col2 = st.columns([2, 1])

with col1:
    # Model selection UI: let the user choose which Document Intelligence model to use
    model_options = []
    # start with env/default model
    model_options.append(MODEL_ID)
    for opt in ("prebuilt-layout", "prebuilt-read"):
        if opt not in model_options:
            model_options.append(opt)
    selected_model = st.selectbox("Select Document Intelligence model", options=model_options, index=0, help="Choose which model to use for extraction. 'prebuilt-layout' extracts tables and layout; 'prebuilt-read' focuses on OCR text.")

with col2:
    # AI configuration status hidden per user request
    # (Previously showed Azure/OpenAI configured or warning messages.)
    st.write("")

if not ENDPOINT or not API_KEY:
    st.error("Missing credentials: please add AZURE_DI_ENDPOINT and AZURE_DI_KEY (or AZURE_FORM_RECOGNIZER_ENDPOINT / AZURE_FORM_RECOGNIZER_KEY) to your .env file.")
    st.info("💡 **Demo Mode Available**: You can still upload files to test the UI. The app will simulate OCR results for demonstration purposes.")

# try to detect public IP for diagnostics (non-blocking)
pub_ip = None
try:
    r = requests.get('https://api.ipify.org?format=text', timeout=2)
    if r.status_code == 200:
        pub_ip = r.text.strip()
except Exception:
    pub_ip = None

def call_document_intelligence_ocr(file_bytes: bytes, content_type: str = "application/octet-stream", model_id: str = None):
    """Call Document Intelligence read/OCR model to extract text from document."""
    if not ENDPOINT or not API_KEY:
        # Demo mode - simulate OCR result
        st.warning("🔧 Demo Mode: Simulating OCR results (no real Azure call made)")
        return {
            "status": "succeeded",
            "analyzeResult": {
                "content": "DEMO CONTENT: This is simulated OCR text for testing purposes.\n\nChemical Composition:\nCarbon: 0.25%\nManganese: 1.2%\nSilicon: 0.4%\n\nMaterial Properties:\nYield Strength: 250 MPa\nTensile Strength: 400 MPa\nHardness: 180 HV\n\nTest Results:\nImpact Energy: 45 J\nElongation: 22%",
                "pages": [
                    {
                        "spans": [{"offset": 0, "length": 200}],
                        "words": []
                    }
                ],
                "tables": [
                    {
                        "id": "demo_table_1",
                        "cells": [
                            {"rowIndex": 0, "columnIndex": 0, "content": "Element"},
                            {"rowIndex": 0, "columnIndex": 1, "content": "Percentage"},
                            {"rowIndex": 1, "columnIndex": 0, "content": "Carbon"},
                            {"rowIndex": 1, "columnIndex": 1, "content": "0.25%"},
                            {"rowIndex": 2, "columnIndex": 0, "content": "Manganese"},
                            {"rowIndex": 2, "columnIndex": 1, "content": "1.2%"}
                        ]
                    }
                ]
            }
        }

    # Allow caller to override the model (UI selection). Fall back to default MODEL_ID.
    model_to_use = model_id or MODEL_ID
    analyze_url = f"{ENDPOINT.rstrip('/')}/formrecognizer/documentModels/{model_to_use}:analyze?api-version={API_VERSION}"
    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY,
        "Content-Type": content_type
    }

    resp = requests.post(analyze_url, headers=headers, data=file_bytes)
    if resp.status_code not in (200, 202):
        # Helpful guidance for common 403 caused by networking/firewall rules
        if resp.status_code == 403:
            # try to extract service message
            try:
                body = resp.json()
                svc_msg = body.get("error", {}).get("message", resp.text)
            except Exception:
                svc_msg = resp.text
            # try to detect caller public IP to make it easy to add to allowed IPs
            pub_ip = None
            try:
                r = requests.get('https://api.ipify.org?format=text', timeout=3)
                if r.status_code == 200:
                    pub_ip = r.text.strip()
            except Exception:
                pub_ip = None

            hint = (
                "Access denied (403). This commonly means your Document Intelligence resource has Virtual Network or Firewall restrictions. "
                "Remedies: 1) In the Azure Portal open your Document Intelligence / Cognitive Services resource → Networking, and either enable public access or add your client IP to the allowed IP list; "
                "2) If the resource is configured for private endpoint access, run the app from a VM/Function inside the same VNet or configure a Private Endpoint with proper DNS; "
                "3) For quick testing, add your current public IP to the allowed list (there's an 'Add client IP' button in the portal)."
            )
            if pub_ip:
                hint = f"Your public IP appears to be {pub_ip}. " + hint
                hint += "\n\nPortal tip: open the Networking blade for your Cognitive Services resource and click 'Add client IP' to whitelist this IP."
                hint += "\n\nPortal link template: https://portal.azure.com/#resource/subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group>/providers/Microsoft.CognitiveServices/accounts/<your-account-name>/networking"
            raise RuntimeError(f"Analyze request failed: {resp.status_code} {svc_msg}\n{hint}")
        raise RuntimeError(f"Analyze request failed: {resp.status_code} {resp.text}")

    # Operation location is in headers
    op_location = resp.headers.get("operation-location") or resp.headers.get("Operation-Location")
    if not op_location:
        # Some endpoints return body directly
        return resp.json()

    # Poll for completion
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
    # Try common locations for text content
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

def extract_layout_tables(result_json: dict) -> list:
    """Extract tables from Document Intelligence layout model result."""
    tables = []
    
    def recurse(obj, path=""):
        if isinstance(obj, dict):
            # Look for tables in the result
            if 'tables' in obj and isinstance(obj['tables'], list):
                for i, t in enumerate(obj['tables']):
                    tables.append((path + f"/tables[{i}]", t))
            for k, v in obj.items():
                recurse(v, path + '/' + str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                recurse(v, path + f'[{i}]')
    
    recurse(result_json, '')
    
    # Process tables to extract headers and rows
    processed_tables = []
    for path, tbl in tables:
        headers = []
        rows = []
        
        # Extract table data from cells (Azure layout model format)
        cells = tbl.get('cells') if isinstance(tbl, dict) else None
        if isinstance(cells, list) and len(cells) > 0:
            # Find matrix dimensions
            max_r = max((c.get('rowIndex', 0) for c in cells), default=0)
            max_c = max((c.get('columnIndex', 0) for c in cells), default=0)
            
            # Create matrix
            matrix = [['' for _ in range(max_c + 1)] for _ in range(max_r + 1)]
            for c in cells:
                r = c.get('rowIndex', 0)
                ci = c.get('columnIndex', 0)
                txt = c.get('content') or c.get('text') or ''
                if r < len(matrix) and ci < len(matrix[r]):
                    matrix[r][ci] = txt
            
            # Extract headers and rows
            if len(matrix) > 0:
                headers = matrix[0]
                rows = matrix[1:] if len(matrix) > 1 else []
        
        processed_tables.append({
            'section': path,
            'table_id': tbl.get('id', ''),
            'headers': headers,
            'rows': rows,
            'raw_table': tbl
        })
    
    return processed_tables

def categorize_tables_with_ai(tables: list, timeout: int = 30) -> Optional[dict]:
    """Ask an LLM to categorize extracted tables into chemical composition and material properties.
    Returns a dict with 'chemical' and 'material' keys containing relevant tables.
    """
    if not tables:
        return None
        
    system_msg = (
        "You are a materials science assistant that categorizes tables from technical documents.\n"
        "Given a list of extracted tables, categorize them into:\n"
        "- 'chemical': Tables containing chemical composition, elemental analysis, chemical properties\n"
        "- 'material': Tables containing mechanical properties, physical properties, test results\n"
        "- 'other': Tables that don't fit the above categories\n"
        "Return a JSON object with keys 'chemical', 'material', 'other', each containing arrays of table objects.\n"
        "For each table, clean up the headers and rows to make them more readable if needed.\n"
        "Output must be valid JSON only (no surrounding explanation)."
    )

    user_msg = f"TABLES TO CATEGORIZE:\n{json.dumps(tables, indent=2)}\n\nReturn the categorized tables as described."

    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": 3000,
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
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"AI call failed: {resp.status_code} {resp.text}")
            body = resp.json()
            content = body.get("choices", [])[0].get("message", {}).get("content")
        else:
            return None

        if not content:
            return None

        # Try to find JSON object in the response
        parsed = find_json_in_text(content.replace('[', '{').replace(']', '}'))  # Handle both array and object responses
        if not parsed:
            # Try parsing as JSON object directly
            try:
                parsed = json.loads(content)
            except:
                return None
        
        return parsed
    except Exception as e:
        st.error(f"AI table categorization failed: {e}")
        return None

def find_json_in_text(s: str):
    """Find the first balanced JSON object or array in a string and parse it."""
    import re
    
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

def extract_properties_with_ai(text: str, timeout: int = 30) -> Optional[list]:
    """Ask an LLM to extract material and chemical properties from OCR text.
    Returns a list of property objects or None on failure.
    Uses temperature 0 to minimize hallucination.
    """
    system_msg = (
        "You are a materials science assistant that extracts chemical and material properties from document text.\n"
        "Given the OCR TEXT, identify and extract all material properties and chemical properties mentioned.\n"
        "Return a JSON array of objects, each with keys: category, property, value, unit, notes.\n"
        "- category: 'chemical' for chemical composition/properties, 'material' for physical/mechanical properties\n"
        "- property: name of the property (e.g., 'Carbon Content', 'Yield Strength', 'Hardness')\n"
        "- value: the extracted value as string\n"
        "- unit: unit if available (e.g., '%', 'psi', 'MPa', 'HV') otherwise empty string\n"
        "- notes: any additional context or location in text\n"
        "Only extract properties that are explicitly mentioned in the text. Do not infer or hallucinate values.\n"
        "Output must be valid JSON only (no surrounding explanation)."
    )

    user_msg = f"OCR TEXT:\n{text[:50000]}\n\nReturn the JSON array of extracted properties."

    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,  # Set to 0 to minimize hallucination
        "max_tokens": 2000,
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
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"AI call failed: {resp.status_code} {resp.text}")
            body = resp.json()
            content = body.get("choices", [])[0].get("message", {}).get("content")
        else:
            return None

        if not content:
            return None

        # Try to find JSON array in the response
        parsed = find_json_in_text(content)
        return parsed
    except Exception as e:
        st.error(f"AI properties extraction failed: {e}")
        return None

def generate_tables_with_ai(text: str, timeout: int = 30) -> Optional[dict]:
    """Ask an LLM to generate tables from OCR text when layout model doesn't detect suitable tables.
    Returns a dict with 'chemical' and 'material' keys containing generated table objects.
    """
    system_msg = (
        "You are a materials science assistant that creates structured tables from document text.\n"
        "Given the OCR TEXT, analyze it and create well-organized tables for:\n"
        "- 'chemical': Chemical composition data, elemental analysis, chemical properties\n"
        "- 'material': Mechanical properties, physical properties, test results\n"
        "Return a JSON object with keys 'chemical', 'material', each containing arrays of table objects.\n"
        "Each table object should have: table_name, headers (array), rows (array of arrays).\n"
        "Only create tables if you find relevant data. Don't create empty or speculative tables.\n"
        "Output must be valid JSON only (no surrounding explanation)."
    )

    user_msg = f"OCR TEXT:\n{text[:50000]}\n\nGenerate structured tables from this text as described."

    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": 3000,
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
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"AI call failed: {resp.status_code} {resp.text}")
            body = resp.json()
            content = body.get("choices", [])[0].get("message", {}).get("content")
        else:
            return None

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
        st.error(f"AI table generation failed: {e}")
        return None

def display_ai_generated_tables(ai_tables: dict, uploaded_file, extracted_text: str):
    """Display AI-generated tables."""
    st.success("✓ Generated tables using AI from OCR text")
    
    # Display Chemical Composition tables
    chemical_tables = ai_tables.get('chemical', [])
    if chemical_tables:
        st.subheader("Chemical Composition Tables (AI Generated)")
        for idx, table in enumerate(chemical_tables):
            table_name = table.get('table_name', f"Generated Chemical Table {idx+1}")
            st.markdown(f"**{table_name}**")
            headers = table.get('headers', [])
            rows = table.get('rows', [])
            
            if headers and rows:
                # Create display data
                display_data = []
                for row in rows:
                    if row:  # Skip empty rows
                        row_dict = {}
                        for i, header in enumerate(headers):
                            value = row[i] if i < len(row) else ""
                            row_dict[str(header)] = str(value)
                        display_data.append(row_dict)
                
                if display_data:
                    st.table(display_data)
                else:
                    st.info("Table generated but no data to display")
            else:
                st.info("Table structure could not be generated properly")
    
    # Display Material Properties tables
    material_tables = ai_tables.get('material', [])
    if material_tables:
        st.subheader("Material Properties Tables (AI Generated)")
        for idx, table in enumerate(material_tables):
            table_name = table.get('table_name', f"Generated Material Table {idx+1}")
            st.markdown(f"**{table_name}**")
            headers = table.get('headers', [])
            rows = table.get('rows', [])
            
            if headers and rows:
                # Create display data
                display_data = []
                for row in rows:
                    if row:  # Skip empty rows
                        row_dict = {}
                        for i, header in enumerate(headers):
                            value = row[i] if i < len(row) else ""
                            row_dict[str(header)] = str(value)
                        display_data.append(row_dict)
                
                if display_data:
                    st.table(display_data)
                else:
                    st.info("Table generated but no data to display")
            else:
                st.info("Table structure could not be generated properly")
    
    # Generate JSON from AI tables
    st.write("**Generating JSON file from AI-generated tables...**")
    # Convert AI tables to format compatible with extract_values_from_tables_and_text
    all_tables = []
    for table in chemical_tables + material_tables:
        all_tables.append({
            'headers': table.get('headers', []),
            'rows': table.get('rows', [])
        })
    
    extracted_data = extract_values_from_tables_and_text(all_tables, extracted_text)
    generated_json = generate_json_from_template(extracted_data, uploaded_file.name if uploaded_file else 'document')
    st.success("✓ Generated JSON file using sample.json template")
    
    # Show preview of generated JSON
    with st.expander("Preview Generated JSON"):
        st.json(generated_json)
    
    # Provide downloads
    base_name = os.path.splitext(uploaded_file.name)[0] if uploaded_file is not None and getattr(uploaded_file, 'name', None) else 'document'
    
    col1, col2, col3 = st.columns(3)
    with col1:
        json_fname = f"{base_name}.mtr.json"
        st.download_button(
            "📋 Download MTR JSON", 
            data=json.dumps(generated_json, indent=2), 
            file_name=json_fname, 
            mime="application/json"
        )
    
    with col2:
        tables_fname = f"{base_name}.ai_generated_tables.json"
        st.download_button(
            "📊 Download AI Generated Tables", 
            data=json.dumps(ai_tables, indent=2), 
            file_name=tables_fname, 
            mime="application/json"
        )
    
    with col3:
        text_fname = f"{base_name}.extracted_text.txt"
        st.download_button(
            "📄 Download Extracted Text", 
            data=extracted_text, 
            file_name=text_fname, 
            mime="text/plain"
        )

def load_sample_json_template():
    """Load the sample JSON template structure."""
    try:
        sample_path = os.path.join(os.path.dirname(__file__), "Sample json", "sample.json")
        with open(sample_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.warning(f"Could not load sample.json template: {e}")
        # Fallback minimal template
        return {
            "CompanyMTRFileID": 0,
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

def extract_values_from_tables_and_text(tables: list, extracted_text: str) -> dict:
    """Extract values from tables and text to populate JSON template."""
    extracted_data = {
        "chemical_composition": {},
        "tensile_properties": {},
        "hardness": {},
        "cvn_properties": {},
        "general_info": {}
    }
    
    # Extract from tables first
    for table in tables:
        headers = table.get('headers', [])
        rows = table.get('rows', [])
        
        if not headers or not rows:
            continue
            
        # Process each row
        for row in rows:
            if len(row) >= 2:
                prop_name = str(row[0]).strip().lower()
                prop_value = str(row[1]).strip()
                
                # Chemical elements mapping
                chemical_mapping = {
                    'carbon': 'C', 'c': 'C',
                    'manganese': 'Mn', 'mn': 'Mn',
                    'phosphorus': 'P', 'p': 'P',
                    'sulfur': 'S', 's': 'S', 'sulphur': 'S',
                    'silicon': 'Si', 'si': 'Si',
                    'niobium': 'CbNb', 'nb': 'CbNb', 'columbium': 'CbNb',
                    'titanium': 'Ti', 'ti': 'Ti',
                    'copper': 'Cu', 'cu': 'Cu',
                    'nickel': 'Ni', 'ni': 'Ni',
                    'molybdenum': 'Mo', 'mo': 'Mo',
                    'chromium': 'Cr', 'cr': 'Cr',
                    'vanadium': 'V', 'v': 'V',
                    'aluminum': 'Al', 'al': 'Al', 'aluminium': 'Al',
                    'boron': 'B', 'b': 'B',
                    'nitrogen': 'N', 'n': 'N',
                    'calcium': 'Ca', 'ca': 'Ca'
                }
                
                # Check if it's a chemical element
                for key, symbol in chemical_mapping.items():
                    if key in prop_name:
                        # Clean percentage sign and extract numeric value
                        clean_value = re.sub(r'[%\s]', '', prop_value)
                        try:
                            float(clean_value)  # Validate it's numeric
                            extracted_data["chemical_composition"][symbol] = clean_value
                        except ValueError:
                            pass
                        break
                
                # Tensile properties
                if any(keyword in prop_name for keyword in ['yield', 'tensile', 'strength', 'elongation']):
                    if 'yield' in prop_name:
                        clean_value = re.sub(r'[^\d.]', '', prop_value)
                        try:
                            float(clean_value)
                            extracted_data["tensile_properties"]["YieldStrength"] = clean_value
                        except ValueError:
                            pass
                    elif 'tensile' in prop_name or 'ultimate' in prop_name:
                        clean_value = re.sub(r'[^\d.]', '', prop_value)
                        try:
                            float(clean_value)
                            extracted_data["tensile_properties"]["UltimateTensileStrength"] = clean_value
                        except ValueError:
                            pass
                    elif 'elongation' in prop_name:
                        clean_value = re.sub(r'[%\s]', '', prop_value)
                        try:
                            float(clean_value)
                            extracted_data["tensile_properties"]["ElongationPercentage"] = clean_value
                        except ValueError:
                            pass
                
                # Hardness
                if 'hardness' in prop_name:
                    clean_value = re.sub(r'[^\d.]', '', prop_value)
                    try:
                        float(clean_value)
                        extracted_data["hardness"]["MaximumHardness"] = clean_value
                    except ValueError:
                        pass
                
                # CVN/Impact properties
                if any(keyword in prop_name for keyword in ['impact', 'cvn', 'charpy', 'energy']):
                    clean_value = re.sub(r'[^\d.]', '', prop_value)
                    try:
                        float(clean_value)
                        extracted_data["cvn_properties"]["CVNAbsorbedEnergyAverage"] = clean_value
                    except ValueError:
                        pass
    
    # Extract additional info from text using regex patterns
    text_lower = extracted_text.lower()
    
    # Try to find heat number
    heat_patterns = [r'heat\s*(?:no|number|#)?\s*:?\s*([a-z0-9]+)', r'heat\s+([a-z0-9]+)']
    for pattern in heat_patterns:
        match = re.search(pattern, text_lower)
        if match:
            extracted_data["general_info"]["HeatNumber"] = match.group(1).upper()
            break
    
    # Try to find grade
    grade_patterns = [r'grade\s*:?\s*([a-z0-9]+)', r'api\s*5l\s*([a-z0-9]+)', r'x(\d+)']
    for pattern in grade_patterns:
        match = re.search(pattern, text_lower)
        if match:
            extracted_data["general_info"]["Grade"] = match.group(1).upper()
            break
    
    return extracted_data

def generate_json_from_template(extracted_data: dict, uploaded_filename: str = "document") -> dict:
    """Generate JSON using sample.json template and extracted data."""
    template = load_sample_json_template()
    
    # Update top-level fields
    current_date = datetime.now().strftime("%m/%d/%Y")
    template["CertificationDate"] = current_date
    
    if "HeatNumber" in extracted_data["general_info"]:
        template["HeatNumber"] = extracted_data["general_info"]["HeatNumber"]
    else:
        template["HeatNumber"] = "EXTRACTED_" + datetime.now().strftime("%Y%m%d")
    
    # Update pipe details (assuming single pipe for now)
    if template.get("HNPipeDetails") and len(template["HNPipeDetails"]) > 0:
        pipe_detail = template["HNPipeDetails"][0]
        
        # Update general pipe info
        if "Grade" in extracted_data["general_info"]:
            pipe_detail["Grade"] = extracted_data["general_info"]["Grade"]
        
        pipe_detail["PipeNumber"] = os.path.splitext(uploaded_filename)[0].upper()
        
        # Update chemical composition (Heat)
        heat_chem = pipe_detail.get("HNPipeHeatChemicalResults", {})
        for element, value in extracted_data["chemical_composition"].items():
            if element == 'C':
                heat_chem["HeatC"] = value
            elif element == 'Mn':
                heat_chem["HeatMn"] = value
            elif element == 'P':
                heat_chem["HeatP"] = value
            elif element == 'S':
                heat_chem["HeatS"] = value
            elif element == 'Si':
                heat_chem["HeatSi"] = value
            elif element == 'CbNb':
                heat_chem["HeatCbNb"] = value
            elif element == 'Ti':
                heat_chem["HeatTi"] = value
            elif element == 'Cu':
                heat_chem["HeatCu"] = value
            elif element == 'Ni':
                heat_chem["HeatNi"] = value
            elif element == 'Mo':
                heat_chem["HeatMo"] = value
            elif element == 'Cr':
                heat_chem["HeatCr"] = value
            elif element == 'V':
                heat_chem["HeatV"] = value
            elif element == 'Al':
                heat_chem["HeatAl"] = value
            elif element == 'B':
                heat_chem["HeatB"] = value
            elif element == 'N':
                heat_chem["HeatN"] = value
            elif element == 'Ca':
                heat_chem["HeatCa"] = value
        
        # Update chemical composition (Product)
        product_chem = pipe_detail.get("HNPipeChemicalCompResults", {})
        for element, value in extracted_data["chemical_composition"].items():
            if element == 'C':
                product_chem["Product1C"] = value
                product_chem["Product2C"] = value
            elif element == 'Mn':
                product_chem["Product1Mn"] = value
                product_chem["Product2Mn"] = value
            elif element == 'P':
                product_chem["Product1P"] = value
                product_chem["Product2P"] = value
            elif element == 'S':
                product_chem["Product1S"] = value
                product_chem["Product2S"] = value
            elif element == 'Si':
                product_chem["Product1Si"] = value
                product_chem["Product2Si"] = value
            elif element == 'CbNb':
                product_chem["Product1CbNb"] = value
                product_chem["Product2CbNb"] = value
            # Add other elements as needed...
        
        # Update tensile test results
        tensile_results = pipe_detail.get("HNPipeTensileTestResults", {})
        for prop, value in extracted_data["tensile_properties"].items():
            if prop in tensile_results:
                tensile_results[prop] = value
        
        # Update hardness results
        hardness_results = pipe_detail.get("HNPipeHardnessResults", {})
        for prop, value in extracted_data["hardness"].items():
            if prop in hardness_results:
                hardness_results[prop] = value
        
        # Update CVN results
        cvn_results = pipe_detail.get("HNPipeCVNResults", {})
        for prop, value in extracted_data["cvn_properties"].items():
            if prop in cvn_results:
                cvn_results[prop] = value
    
    return template

def display_properties_fallback(properties: list, uploaded_file, extracted_text: str):
    """Display properties in the original format as fallback."""
    if not properties:
        st.warning("No properties extracted from the document.")
        return
        
    st.subheader("Extracted Material & Chemical Properties")
    
    # Separate by category
    chemical_props = [p for p in properties if p.get("category", "").lower() == "chemical"]
    material_props = [p for p in properties if p.get("category", "").lower() == "material"]
    other_props = [p for p in properties if p.get("category", "").lower() not in ["chemical", "material"]]
    
    if chemical_props:
        st.markdown("**Chemical Composition:**")
        chem_rows = []
        for prop in chemical_props:
            value = prop.get("value", "")
            unit = prop.get("unit", "")
            # Combine value and unit for cleaner display
            display_value = f"{value} {unit}".strip() if unit else value
            chem_rows.append({
                "Property": prop.get("property", ""),
                "Value": display_value
            })
        st.table(chem_rows)
    
    if material_props:
        st.markdown("**Material Properties:**")
        mat_rows = []
        for prop in material_props:
            value = prop.get("value", "")
            unit = prop.get("unit", "")
            # Combine value and unit for cleaner display
            display_value = f"{value} {unit}".strip() if unit else value
            mat_rows.append({
                "Property": prop.get("property", ""),
                "Value": display_value
            })
        st.table(mat_rows)
    
    if other_props:
        st.markdown("**Other Properties:**")
        other_rows = []
        for prop in other_props:
            value = prop.get("value", "")
            unit = prop.get("unit", "")
            # Combine value and unit for cleaner display
            display_value = f"{value} {unit}".strip() if unit else value
            other_rows.append({
                "Property": prop.get("property", ""),
                "Value": display_value
            })
        st.table(other_rows)
    
    # Generate JSON from properties
    st.write("**Generating JSON file from extracted properties...**")
    # Convert properties to table format for processing
    mock_tables = []
    for prop in properties:
        mock_tables.append({
            'headers': ['Property', 'Value'],
            'rows': [[prop.get('property', ''), prop.get('value', '')]]
        })
    
    extracted_data = extract_values_from_tables_and_text(mock_tables, extracted_text)
    generated_json = generate_json_from_template(extracted_data, uploaded_file.name if uploaded_file else 'document')
    st.success("✓ Generated JSON file using sample.json template")
    
    # Show preview of generated JSON
    with st.expander("Preview Generated JSON"):
        st.json(generated_json)
    
    # Provide downloads
    base_name = os.path.splitext(uploaded_file.name)[0] if uploaded_file is not None and getattr(uploaded_file, 'name', None) else 'document'
    
    col1, col2, col3 = st.columns(3)
    with col1:
        json_fname = f"{base_name}.mtr.json"
        st.download_button(
            "📋 Download MTR JSON", 
            data=json.dumps(generated_json, indent=2), 
            file_name=json_fname, 
            mime="application/json"
        )
    
    with col2:
        props_fname = f"{base_name}.properties.json"
        st.download_button(
            "📊 Download Properties JSON", 
            data=json.dumps(properties, indent=2), 
            file_name=props_fname, 
            mime="application/json"
        )
    
    with col3:
        text_fname = f"{base_name}.extracted_text.txt"
        st.download_button(
            "📄 Download Extracted Text", 
            data=extracted_text, 
            file_name=text_fname, 
            mime="text/plain"
        )

# Streamlit layout
uploaded_file = st.file_uploader("Upload document (PDF / JPG / PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=False)
run_button = st.button("Run Smart Analysis (Selected Model → AI)")

if uploaded_file is not None:
    st.write(f"Uploaded: {uploaded_file.name} ({uploaded_file.type})")

if run_button:
    if uploaded_file is None:
        st.warning("Please upload a file before running.")
    else:
        with st.spinner("Running smart analysis (Selected Model → AI)..."):
            try:
                file_bytes = uploaded_file.read()
                
                # Step 1: Run selected Document Intelligence model
                st.write(f"**Step 1:** Running Document Intelligence model `{selected_model}` to extract text and layout...")
                ocr_result = call_document_intelligence_ocr(file_bytes, content_type=uploaded_file.type or "application/octet-stream", model_id=selected_model)
                
                # Step 2: Extract text and tables from result
                extracted_text = extract_text_from_ocr_result(ocr_result)
                if not extracted_text.strip():
                    st.error("No text was extracted from the document. The document may be empty or the OCR failed.")
                    st.stop()
                
                st.success(f"✓ Extracted {len(extracted_text)} characters of text")
                
                # Extract layout tables
                layout_tables = extract_layout_tables(ocr_result)
                st.success(f"✓ Found {len(layout_tables)} tables using {selected_model} model")
                
                # Show a preview of extracted text
                with st.expander("Preview extracted text (first 1000 characters)"):
                    st.text(extracted_text[:1000] + "..." if len(extracted_text) > 1000 else extracted_text)
                
                # Step 3: Use AI to process the extracted data
                st.write("**Step 2:** Using AI to categorize extracted tables and generate structured data...")
                
                if layout_tables:
                    # Categorize tables with AI
                    categorized_tables = categorize_tables_with_ai(layout_tables)
                    
                    if categorized_tables and (categorized_tables.get('chemical') or categorized_tables.get('material')):
                        st.success(f"✓ Successfully categorized tables: {len(categorized_tables.get('chemical', []))} chemical, {len(categorized_tables.get('material', []))} material")
                        
                        # Display Chemical Composition tables
                        chemical_tables = categorized_tables.get('chemical', [])
                        if chemical_tables:
                            st.subheader("Chemical Composition Tables")
                            for idx, table in enumerate(chemical_tables):
                                table_name = table.get('table_id') or f"Chemical Table {idx+1}"
                                st.markdown(f"**{table_name}**")
                                headers = table.get('headers', [])
                                rows = table.get('rows', [])
                                
                                if headers and rows:
                                    # Create display data
                                    display_data = []
                                    for row in rows:
                                        if row:  # Skip empty rows
                                            row_dict = {}
                                            for i, header in enumerate(headers):
                                                value = row[i] if i < len(row) else ""
                                                row_dict[str(header)] = str(value)
                                            display_data.append(row_dict)
                                    
                                    if display_data:
                                        st.table(display_data)
                                    else:
                                        st.info("Table found but no data to display")
                                else:
                                    st.info("Table structure could not be parsed")
                        
                        # Display Material Properties tables
                        material_tables = categorized_tables.get('material', [])
                        if material_tables:
                            st.subheader("Material Properties Tables")
                            for idx, table in enumerate(material_tables):
                                table_name = table.get('table_id') or f"Material Table {idx+1}"
                                st.markdown(f"**{table_name}**")
                                headers = table.get('headers', [])
                                rows = table.get('rows', [])
                                
                                if headers and rows:
                                    # Create display data
                                    display_data = []
                                    for row in rows:
                                        if row:  # Skip empty rows
                                            row_dict = {}
                                            for i, header in enumerate(headers):
                                                value = row[i] if i < len(row) else ""
                                                row_dict[str(header)] = str(value)
                                            display_data.append(row_dict)
                                    
                                    if display_data:
                                        st.table(display_data)
                                    else:
                                        st.info("Table found but no data to display")
                                else:
                                    st.info("Table structure could not be parsed")
                        
                        # Display Other tables if any
                        other_tables = categorized_tables.get('other', [])
                        if other_tables:
                            with st.expander("Other Tables"):
                                for idx, table in enumerate(other_tables):
                                    table_name = table.get('table_id') or f"Other Table {idx+1}"
                                    st.markdown(f"**{table_name}**")
                                    headers = table.get('headers', [])
                                    rows = table.get('rows', [])
                                    
                                    if headers and rows:
                                        # Create display data
                                        display_data = []
                                        for row in rows:
                                            if row:  # Skip empty rows
                                                row_dict = {}
                                                for i, header in enumerate(headers):
                                                    value = row[i] if i < len(row) else ""
                                                    row_dict[str(header)] = str(value)
                                                display_data.append(row_dict)
                                        
                                        if display_data:
                                            st.table(display_data)
                        
                        # Generate JSON from extracted data
                        st.write("**Step 3:** Generating JSON file from extracted data...")
                        all_tables = chemical_tables + material_tables + other_tables
                        extracted_data = extract_values_from_tables_and_text(all_tables, extracted_text)
                        generated_json = generate_json_from_template(extracted_data, uploaded_file.name)
                        st.success("✓ Generated JSON file using sample.json template")
                        
                        # Show preview of generated JSON
                        with st.expander("Preview Generated JSON"):
                            st.json(generated_json)
                        
                        # Provide downloads
                        base_name = os.path.splitext(uploaded_file.name)[0] if uploaded_file is not None and getattr(uploaded_file, 'name', None) else 'document'
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            json_fname = f"{base_name}.mtr.json"
                            st.download_button(
                                "📋 Download MTR JSON", 
                                data=json.dumps(generated_json, indent=2), 
                                file_name=json_fname, 
                                mime="application/json"
                            )
                        
                        with col2:
                            tables_fname = f"{base_name}.categorized_tables.json"
                            st.download_button(
                                "📊 Download Categorized Tables", 
                                data=json.dumps(categorized_tables, indent=2), 
                                file_name=tables_fname, 
                                mime="application/json"
                            )
                        
                        with col3:
                            raw_tables_fname = f"{base_name}.raw_tables.json"
                            st.download_button(
                                "🔍 Download Raw Tables", 
                                data=json.dumps(layout_tables, indent=2), 
                                file_name=raw_tables_fname, 
                                mime="application/json"
                            )
                        
                        with col4:
                            text_fname = f"{base_name}.extracted_text.txt"
                            st.download_button(
                                "📄 Download Extracted Text", 
                                data=extracted_text, 
                                file_name=text_fname, 
                                mime="text/plain"
                            )
                    else:
                        # Generate AI tables from text if categorization fails
                        ai_generated_tables = generate_tables_with_ai(extracted_text)
                        if ai_generated_tables and (ai_generated_tables.get('chemical') or ai_generated_tables.get('material')):
                            display_ai_generated_tables(ai_generated_tables, uploaded_file, extracted_text)
                        else:
                            st.warning("AI could not process the extracted data into meaningful tables.")
                else:
                    # No tables found, generate AI tables from text
                    ai_generated_tables = generate_tables_with_ai(extracted_text)
                    if ai_generated_tables and (ai_generated_tables.get('chemical') or ai_generated_tables.get('material')):
                        display_ai_generated_tables(ai_generated_tables, uploaded_file, extracted_text)
                    else:
                        st.warning("No tables found and AI could not generate meaningful tables from text.")

            except Exception as e:
                msg = str(e)
                # If our earlier networking hint is present, display it prominently
                if 'Virtual Network' in msg or 'Access denied (403)' in msg or 'Firewall' in msg:
                    st.error("Document Intelligence call failed due to networking/firewall restrictions. See details below and follow the remediation steps.")
                    st.markdown("**Details:**")
                    st.code(msg)
                else:
                    st.exception(e)

# If no run yet, show instructions
if not run_button:
    # Removed instruction block and sample JSON expander per user request
    st.info("Upload a document and press Run to extract text and tables. The app will run the selected model and generate JSON using the sample.json template.")
    st.markdown("---")
    st.info("Demo mode available if Azure credentials are missing.")
