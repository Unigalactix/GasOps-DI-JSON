import os
import io
import json
import time
import requests
import streamlit as st
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# Configuration from .env
ENDPOINT = os.getenv("AZURE_DI_ENDPOINT") or os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
API_KEY = os.getenv("AZURE_DI_KEY") or os.getenv("AZURE_FORM_RECOGNIZER_KEY")
# Use read model for OCR
MODEL_ID = os.getenv("AZURE_DI_MODEL_ID", "prebuilt-read")
API_VERSION = os.getenv("AZURE_DI_API_VERSION", "2023-07-31")

st.set_page_config(page_title="OCR → Material Properties Extractor", layout="wide")

st.title("OCR → Material & Chemical Properties Extractor")

if not ENDPOINT or not API_KEY:
    st.error("Missing credentials: please add AZURE_DI_ENDPOINT and AZURE_DI_KEY (or AZURE_FORM_RECOGNIZER_ENDPOINT / AZURE_FORM_RECOGNIZER_KEY) to your .env file.")

# try to detect public IP for diagnostics (non-blocking)
pub_ip = None
try:
    r = requests.get('https://api.ipify.org?format=text', timeout=2)
    if r.status_code == 200:
        pub_ip = r.text.strip()
except Exception:
    pub_ip = None

if pub_ip:
    st.sidebar.markdown(f"**Detected public IP:** `{pub_ip}`")
    st.sidebar.markdown("If you get a 403, add this IP to the Networking → Allowed IPs in the Azure Portal.")

# AI helpers (Azure OpenAI or OpenAI)
def _has_azure_openai():
    return bool(os.getenv("AZURE_OPENAI_ENDPOINT") and (os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")) and os.getenv("AZURE_OPENAI_DEPLOYMENT"))

def _has_openai_key():
    return bool(os.getenv("OPENAI_API_KEY"))

def call_document_intelligence_ocr(file_bytes: bytes, content_type: str = "application/octet-stream"):
    """Call Document Intelligence read/OCR model to extract text from document."""
    if not ENDPOINT or not API_KEY:
        raise RuntimeError("Missing endpoint or API key")

    analyze_url = f"{ENDPOINT.rstrip('/')}/formrecognizer/documentModels/{MODEL_ID}:analyze?api-version={API_VERSION}"
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

def find_json_in_text(s: str):
    """Find the first balanced JSON object in a string and parse it."""
    import re
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
        st.sidebar.error(f"AI properties extraction failed: {e}")
        return None

# Streamlit layout
st.sidebar.header("OCR Settings")
st.sidebar.write("Model: %s" % MODEL_ID)

# Show AI configuration status
if _has_azure_openai():
    st.sidebar.success("✓ Azure OpenAI configured")
elif _has_openai_key():
    st.sidebar.success("✓ OpenAI configured")
else:
    st.sidebar.warning("⚠ No AI credentials found - add AZURE_OPENAI_* or OPENAI_API_KEY to .env")

uploaded_file = st.file_uploader("Upload document (PDF / JPG / PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=False)
run_button = st.button("Run OCR + AI extraction")

if uploaded_file is not None:
    st.sidebar.write(f"Uploaded: {uploaded_file.name} ({uploaded_file.type})")

if run_button:
    if uploaded_file is None:
        st.warning("Please upload a file before running.")
    else:
        with st.spinner("Running OCR and extracting properties..."):
            try:
                file_bytes = uploaded_file.read()
                
                # Step 1: OCR with Document Intelligence
                st.write("**Step 1:** Running OCR with Document Intelligence...")
                ocr_result = call_document_intelligence_ocr(file_bytes, content_type=uploaded_file.type or "application/octet-stream")
                
                # Step 2: Extract text from OCR result
                extracted_text = extract_text_from_ocr_result(ocr_result)
                if not extracted_text.strip():
                    st.error("No text was extracted from the document. The document may be empty or the OCR failed.")
                    st.stop()
                
                st.success(f"✓ Extracted {len(extracted_text)} characters of text")
                
                # Show a preview of extracted text
                with st.expander("Preview extracted text (first 1000 characters)"):
                    st.text(extracted_text[:1000] + "..." if len(extracted_text) > 1000 else extracted_text)
                
                # Step 3: AI extraction of properties
                st.write("**Step 2:** Using AI to extract material and chemical properties...")
                properties = extract_properties_with_ai(extracted_text)
                
                if not properties:
                    st.warning("AI did not extract any properties. This could be due to:")
                    st.write("- No AI credentials configured")
                    st.write("- No material/chemical properties found in the text")
                    st.write("- AI response parsing failed")
                    st.stop()
                
                st.success(f"✓ Extracted {len(properties)} properties")
                
                # Step 4: Display results
                st.subheader("Extracted Material & Chemical Properties")
                
                # Separate by category
                chemical_props = [p for p in properties if p.get("category", "").lower() == "chemical"]
                material_props = [p for p in properties if p.get("category", "").lower() == "material"]
                other_props = [p for p in properties if p.get("category", "").lower() not in ["chemical", "material"]]
                
                if chemical_props:
                    st.markdown("**Chemical Properties:**")
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
                
                # Step 5: Provide downloads
                base_name = os.path.splitext(uploaded_file.name)[0] if uploaded_file is not None and getattr(uploaded_file, 'name', None) else 'document'
                
                col1, col2 = st.columns(2)
                with col1:
                    props_fname = f"{base_name}.properties.json"
                    st.download_button(
                        "Download Properties JSON", 
                        data=json.dumps(properties, indent=2), 
                        file_name=props_fname, 
                        mime="application/json"
                    )
                
                with col2:
                    text_fname = f"{base_name}.extracted_text.txt"
                    st.download_button(
                        "Download Extracted Text", 
                        data=extracted_text, 
                        file_name=text_fname, 
                        mime="text/plain"
                    )

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
    st.info("Upload a document and press Run to extract text using Document Intelligence OCR, then use AI to identify material and chemical properties.")
    st.markdown("---")
    # st.subheader("Required Environment Variables")
    # st.markdown("""
    # Add these to your `.env` file:
    
    # **Document Intelligence (required):**
    # - `AZURE_DI_ENDPOINT` - Your Document Intelligence endpoint
    # - `AZURE_DI_KEY` - Your Document Intelligence key
    
    # **AI Service (required for property extraction):**
    # - For Azure OpenAI: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT`
    # - For OpenAI: `OPENAI_API_KEY`
    # """)
