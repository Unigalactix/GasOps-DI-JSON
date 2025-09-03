import os
import io
import json
import time
import re
import requests
import streamlit as st
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# Configuration from .env
ENDPOINT = os.getenv("AZURE_DI_ENDPOINT") or os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
API_KEY = os.getenv("AZURE_DI_KEY") or os.getenv("AZURE_FORM_RECOGNIZER_KEY")
MODEL_ID = os.getenv("AZURE_DI_MODEL_ID", "prebuilt-document")
API_VERSION = os.getenv("AZURE_DI_API_VERSION", "2023-07-31")

st.set_page_config(page_title="Document -> JSON Converter", layout="wide")

st.title("Document Intelligence → JSON Converter")

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
    st.sidebar.markdown("If you get a 403, add this IP to the Networking -> Allowed IPs in the Azure Portal.")

# Load sample template
TEMPLATE_PATH = os.path.join("Sample json", "sample.json")
try:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        SAMPLE_TEMPLATE = json.load(f)
except Exception:
    SAMPLE_TEMPLATE = {}

# Helpers
def call_document_intelligence(file_bytes: bytes, content_type: str = "application/octet-stream"):
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

    # Poll
    for _ in range(60):
        time.sleep(1)
        get_resp = requests.get(op_location, headers={"Ocp-Apim-Subscription-Key": API_KEY})
        if get_resp.status_code not in (200, 201):
            raise RuntimeError(f"Polling failed: {get_resp.status_code} {get_resp.text}")
        j = get_resp.json()
        status = j.get("status")
        if status and status.lower() == "succeeded":
            # result may be in "result" or "analyzeResult"
            return j
        if status and status.lower() in ("failed", "cancelled"):
            raise RuntimeError(f"Analysis {status}: {j}")
    raise RuntimeError("Timed out waiting for analysis to complete")


def find_json_in_text(s: str):
    """Find the first balanced JSON object in a string and parse it."""
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
    return None


def extract_json_from_result(result_json: dict):
    """Try to locate JSON content inside the service result. Return a dict or None."""
    # 1) If top-level contains a result-like object, try to use it directly
    for key in ("result", "analyzeResult", "analyze_result", "documents", "documentResults", "content"):
        if key in result_json:
            candidate = result_json[key]
            if isinstance(candidate, dict):
                return candidate
            # if it's string, try to find JSON inside
            if isinstance(candidate, str):
                parsed = find_json_in_text(candidate)
                if parsed:
                    return parsed

    # 2) Search recursively for any string containing JSON
    def recurse(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                res = recurse(v)
                if res is not None:
                    return res
        elif isinstance(obj, list):
            for v in obj:
                res = recurse(v)
                if res is not None:
                    return res
        elif isinstance(obj, str):
            res = find_json_in_text(obj)
            if res is not None:
                return res
        return None

    return recurse(result_json)


def normalize_key(k: str):
    return re.sub(r"[^a-z0-9]", "", k.lower()) if isinstance(k, str) else k


def overlay_template(template, source):
    """Overlay values from source onto template where keys match (by normalized key names).
    This is a best-effort shallow merge that preserves template structure."""
    if not isinstance(template, (dict, list)):
        return source if source is not None else template

    if isinstance(template, dict):
        out = {}
        # build normalized mapping for source
        source_map = {}
        if isinstance(source, dict):
            for k, v in source.items():
                source_map[normalize_key(k)] = v

        for k, v in template.items():
            nk = normalize_key(k)
            if nk in source_map:
                # If both are dict/array, recurse
                out[k] = overlay_template(v, source_map[nk])
            else:
                # try direct key
                if isinstance(source, dict) and k in source:
                    out[k] = overlay_template(v, source[k])
                else:
                    # keep template default
                    out[k] = v
        return out

    if isinstance(template, list):
        # If source is a list, try to map items
        if isinstance(source, list) and len(source) > 0:
            # overlay each template[0] with each source item
            item_template = template[0] if len(template) > 0 else {}
            out_list = []
            for s in source:
                out_list.append(overlay_template(item_template, s))
            return out_list
        else:
            # fallback: keep template
            return template


# AI conversion helpers
def _has_azure_openai():
    return bool(os.getenv("AZURE_OPENAI_ENDPOINT") and (os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")) and os.getenv("AZURE_OPENAI_DEPLOYMENT"))


def _has_openai_key():
    return bool(os.getenv("OPENAI_API_KEY"))


def convert_with_ai(source_json: dict, template_json: dict, timeout: int = 30) -> Optional[dict]:
    """Ask an LLM (OpenAI or Azure OpenAI) to convert source_json into the shape of template_json.
    Returns parsed JSON dict on success or None on failure.
    """
    # Prepare prompt
    system_msg = (
        "You are a JSON transformation assistant.\n"
        "Input: a target JSON template and a source JSON extracted from a document.\n"
        "Task: produce a single JSON object that follows the template structure (same keys and nesting), filling values using information from the source JSON when possible.\n"
        "Rules:\n"
        " - Output must be valid JSON only (no surrounding explanation).\n"
        " - Preserve template keys and types. If a value cannot be found in the source, keep the template value.\n"
        " - Keep arrays in the template: populate elements where mapping is possible.\n"
        " - Do not invent additional top-level keys.\n"
    )

    user_msg = (
        "TARGET TEMPLATE:\n" + json.dumps(template_json, indent=2) + "\n\n"
        "SOURCE JSON (extracted):\n" + json.dumps(source_json, indent=2) + "\n\n"
        "Return the transformed JSON that matches the TARGET TEMPLATE exactly (keys and nesting)."
    )

    payload = {
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0,
        "max_tokens": 1500,
    }

    # Choose provider
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
            # Azure/OpenAI compatible response shape
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

        parsed = find_json_in_text(content)
        return parsed
    except Exception as e:
        # don't crash the app - caller will fallback
        st.sidebar.error(f"AI conversion failed: {e}")
        return None


# Streamlit layout
st.sidebar.header("Run settings")
st.sidebar.write("Model: %s" % MODEL_ID)

uploaded_file = st.file_uploader("Upload document (PDF / JPG / PNG)", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=False)
run_button = st.button("Run extraction")

if uploaded_file is not None:
    st.sidebar.write(f"Uploaded: {uploaded_file.name} ({uploaded_file.type})")

if run_button:
    if uploaded_file is None:
        st.warning("Please upload a file before running.")
    else:
        with st.spinner("Sending to Document Intelligence and extracting JSON..."):
            try:
                file_bytes = uploaded_file.read()
                result = call_document_intelligence(file_bytes, content_type=uploaded_file.type or "application/octet-stream")

                # extract JSON from result
                extracted = extract_json_from_result(result)
                if extracted is None:
                    # fallback: present the whole result
                    extracted = result

                # If the extracted is nested under operation result, it may be the whole body
                # Try AI-based conversion first (OpenAI/Azure OpenAI), fall back to overlay_template
                converted = None
                ai_result = convert_with_ai(extracted, SAMPLE_TEMPLATE)
                if isinstance(ai_result, dict):
                    converted = ai_result
                else:
                    converted = overlay_template(SAMPLE_TEMPLATE, extracted)

                # Show results side-by-side
                # Use uploaded file base name for downloads (e.g. mydoc.pdf -> mydoc.json)
                base_name = os.path.splitext(uploaded_file.name)[0] if uploaded_file is not None and getattr(uploaded_file, 'name', None) else 'document'
                extracted_fname = f"{base_name}.extracted.json"
                converted_fname = f"{base_name}.converted.json"

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("1) Extracted JSON (from result)")
                    st.download_button("Download extracted JSON", data=json.dumps(extracted, indent=2), file_name=extracted_fname, mime="application/json")
                    st.json(extracted)
                with col2:
                    st.subheader("2) Converted JSON (sample format)")
                    st.download_button("Download converted JSON", data=json.dumps(converted, indent=2), file_name=converted_fname, mime="application/json")
                    st.json(converted)

            except Exception as e:
                msg = str(e)
                # If our earlier networking hint is present, display it prominently
                if 'Virtual Network' in msg or 'Access denied (403)' in msg or 'Firewall' in msg:
                    st.error("Document Intelligence call failed due to networking/firewall restrictions. See details below and follow the remediation steps.")
                    st.markdown("**Details:**")
                    st.code(msg)
                else:
                    st.exception(e)


# If no run yet, show template and instructions
if not run_button:
    st.info("Upload a document and press Run to analyze with Azure Document Intelligence. The app will try to extract any JSON contained in the analysis result and then map it onto the sample template from 'Sample json/sample.json'.")
    st.markdown("---")
    st.subheader("Sample template (editable file: Sample json/sample.json)")
    st.code(json.dumps(SAMPLE_TEMPLATE, indent=2), language="json")
