# PDF Document Intelligence Processor

An interactive application that processes PDF files using Azure Document Intelligence and AI to generate structured JSON output based on a template.

## Features

- Interactive command-line interface - just run and follow prompts
- Processes PDF files using Azure Document Intelligence (prebuilt-read model)
- Uses AI (Azure OpenAI or OpenAI) to extract and structure data
- Generates JSON output based on the sample.json template
- Built-in error handling and validation
- Option to process multiple files in one session

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure credentials in `.env` file:
```bash
# Azure Document Intelligence
AZURE_DI_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com/
AZURE_DI_KEY=your_32_character_api_key_here

# AI Configuration (choose one)
# Option 1: Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your_openai_key
AZURE_OPENAI_DEPLOYMENT=your_deployment_name

# PDF Document Intelligence Processor

An interactive toolchain that converts material test report (MTR) PDFs into structured JSON using Azure Document Intelligence (OCR) and AI, with optional API integrations to fetch PDFs by HeatNumber and to POST results back to the database.

## Highlights

- Interactive CLI with multiple flows (local PDF, batch, API by HeatNumber, XLSX update, POST uploader)
- Azure Document Intelligence for OCR + Azure OpenAI/OpenAI for schema mapping
- Ensures JSON includes mandatory fields: CompanyMTRFileID and HeatNumber (API-by-HeatNumber path)
- XLSX updater that merges JSON into a template with simple color logic
- Debug logging for API responses saved in `debug/` on failures

## Versions and environment

- Local Python (this machine): 3.12.x (Windows)
- Recommended Python: >=3.11, <=3.13
- Dependencies are pinned in `requirements.txt` for reproducible installs

Install dependencies (PowerShell):
```powershell
2. Open `.env` in a text editor and paste your keys where shown:
```

## Configure environment (.env)

Create a `.env` in the project root (copy `.env.template` and fill values):

```ini
# Azure Document Intelligence (required)
AZURE_DI_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com/
AZURE_DI_KEY=your_azure_di_key
AZURE_DI_MODEL_ID=prebuilt-document
AZURE_DI_API_VERSION=2023-07-31

# AI (choose one)
# Azure OpenAI
# AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
# AZURE_OPENAI_KEY=your_azure_openai_key
# AZURE_OPENAI_DEPLOYMENT=your_deployment_name
# AZURE_OPENAI_API_VERSION=2023-10-01
# Or OpenAI
# OPENAI_API_KEY=your_openai_api_key

# Auth bootstrap for external API (required for API-based flows)
# Base64 of: LoginMasterID&Database_Name&OrgID
encoded_string=BASE64_LOGINMASTERID_AND_DBNAME_AND_ORGID
```

Note: the scripts read `encoded_string` (lowercase) to derive an API auth token at runtime.

## Entry points

There are two primary CLIs you’ll use from the repo root:

1) Object-oriented processor with API fetch and XLSX mapping (recommended)

```powershell
	- For OCR (Azure Document Intelligence):
	  - `AZURE_DI_ENDPOINT` — e.g. `https://your-resource.cognitiveservices.azure.com/`
	  - `AZURE_DI_KEY` — the secret key for the resource

Key menu options:
- 1: Process a single local PDF → produces JSON
- 2: Process multiple local PDFs → produces JSONs
- 3: JSON → XLSX merge/update (uses template under Sample json/)
- 4: Fetch by HeatNumber via API → OCR+AI → JSON
  - Uses your `encoded_string` to build an auth token automatically
  - Enforces CompanyMTRFileID and HeatNumber in the output JSON
  - On API errors, prints status/body preview and saves full response to `debug/`

2) Standalone uploader (POST JSON to database)

```powershell
	- For AI (choose one):
	  - Azure OpenAI: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT`

Features:
- Scans `Sample json/` for JSON files and posts them to AddUpdateMTRMetadata
- Uses the same auth bootstrap from `encoded_string`
- Certificate-based client auth using `./certificate/oamsapicert2023.pfx`
- “Test API connection” option to validate connectivity quickly

## Certificate

Both API flows (fetch by HeatNumber and posting results) use a client certificate located at:

```
./certificate/oamsapicert2023.pfx
```

Ensure the file exists at that path. The password is set in code as `password1234`. If your certificate or password differs, update the code or provide an override mechanism (future improvement).

## Typical workflow

1) Prepare `.env` with Azure keys and `encoded_string`
2) Run the processor, choose flow:
   - Local PDFs (options 1/2) → JSON goes to `Sample json/`
   - API by HeatNumber (option 4) → PDF is fetched and processed → JSON goes to `Sample json/`
3) Optionally run `post_mtr_data.py` to upload the generated JSONs to the database

## Troubleshooting

- “Invalid API response format”: the tool prints status and a 500-char body preview, and saves the full response under `debug/`. Common causes are invalid/expired token, cert mismatch, or API shape changes.
- “Missing Azure credentials”: set `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` in `.env`.
- “AI did not return valid JSON”: the tool tries to extract JSON; edit the output manually if needed and re-run XLSX update.
If you need help, capture the console output and the debug file path (if any) and share it.

## Developer notes (brief)

- Main CLI: `pdf_processor_new prompt.py` (object-oriented)
- Uploader CLI: `post_mtr_data.py`
- Token/bootstrap helpers: `decryption.py`
- Tests: `TESTS/`

Future ideas: pluggable certificate path/password via env, GUI front-end, stricter validation rules, CI tests.


Q: What if the AI outputs incorrect values?
