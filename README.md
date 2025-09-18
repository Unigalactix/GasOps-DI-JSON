# PDF Document Intelligence Processor (Modular)

Processes MTR PDFs into structured JSON using Azure Document Intelligence (OCR) + AI, with API helpers to fetch PDFs by HeatNumber and POST results back. The codebase is now modular with tiny drivers and a clean `output/` folder for generated files.

## Highlights

- Modular package under `mtr_processor/` and small CLI entry points
- Azure Document Intelligence for OCR; Azure OpenAI/OpenAI optional for mapping
- API fetch by HeatNumber (mTLS + time-based auth token)
- Ensures CompanyMTRFileID and HeatNumber present in API-path JSON
- JSONs saved to `output/` by default (keeps `Sample json/` clean)
- Optional uploader to POST JSONs back to the database
- Debug: raw API responses saved to `debug/` on schema/auth failures

## Folder structure

```
GasOps-DI-JSON/
├─ mtr_processor/
│  ├─ auth/
│  │  └─ tokens.py              # get_default_auth_token() wrapper
│  ├─ api/
│  │  └─ weld_client.py         # WeldAPIClient (requests_pkcs12)
│  ├─ ocr/
│  │  └─ di_ocr.py              # DocumentIntelligenceOCR wrapper
│  ├─ ai/
│  │  └─ template_processor.py  # AITemplateProcessor wrapper
│  ├─ excel/
│  │  └─ xlsx_processor.py      # XLSXProcessor wrapper
│  ├─ pipeline/
│  │  ├─ api_processor.py       # APIProcessor wrapper
│  │  └─ pdf_processor.py       # PDFProcessor wrapper
│  └─ utils/
│     └─ loader.py              # Robust importer for legacy file
├─ cli/
│  ├─ process_heat.py           # Minimal driver: fetch-by-Heat → JSON
│  └─ post_mtr_data.py          # Minimal driver: POST JSONs
├─ output/                      # Generated JSONs and PDFs (default)
├─ debug/                       # Saved raw API responses on failure
├─ pdf_processor_new prompt.py  # Legacy implementations (still used)
├─ post_mtr_data.py             # MTRDataPoster (used by CLI)
├─ decryption.py                # Token decoding + generator
├─ requirements.txt             # Pinned versions
├─ .env.template                # Example environment variables
└─ Sample json/                 # Samples/templates only
```

Note: wrappers import the actual class implementations from `pdf_processor_new prompt.py` to avoid duplication during the transition. We can fully migrate those into `mtr_processor/` next if you want to remove the legacy file.

## Setup

Install dependencies (Windows PowerShell):

```powershell
python -m pip install -r requirements.txt
```

Create `.env` at repo root (copy `.env.template` and fill values):

```ini
# Azure Document Intelligence (required for OCR)
AZURE_DI_ENDPOINT=https://your-resource-name.cognitiveservices.azure.com/
AZURE_DI_KEY=your_azure_di_key
AZURE_DI_MODEL_ID=prebuilt-document
AZURE_DI_API_VERSION=2023-07-31

# AI (optional, choose one)
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

Both `ENCODED_STRING` and `encoded_string` are supported; `encoded_string` is used in most scripts.

## How to run

Process a HeatNumber (fetch PDF via API → OCR/AI → JSON in `output/`):

```powershell
python -m cli.process_heat <HEAT_NUMBER>
```

Optional custom output directory:

```powershell
python -m cli.process_heat <HEAT_NUMBER> "C:\path\to\folder"
```

Post JSONs to the database (defaults to `output/`):

```powershell
python -m cli.post_mtr_data
```

Or interactive uploader:

```powershell
python post_mtr_data.py
```

## Certificate

Both API flows (GET by HeatNumber and POST) use a client certificate:

```
./certificate/oamsapicert2023.pfx
```

Ensure the file exists at that path. The default password is `password1234` in code; update if your cert is different.

## Architecture diagram

```
				 +-----------------------------+
				 |        CLI (Drivers)        |
				 |-----------------------------|
				 | cli/process_heat.py         |
				 | cli/post_mtr_data.py        |
				 +---------------+-------------+
									  |
									  v
					  +-----------+-----------+
					  |        mtr_processor  |
					  |  (modular components) |
					  +-----------+-----------+
									  |
	  +-----------------------+-----------------------+
	  |                       |                       |
	  v                       v                       v
 +---+----+            +-----+------+          +-----+------+
 |  ocr   |            |   api      |          |   excel    |
 | di_ocr |            | weld_client|          | xlsx_proc  |
 +---+----+            +-----+------+          +-----+------+
	  |                       |                       |
	  v                       v                       v
 DocumentIntelligence  requests_pkcs12+mTLS     openpyxl template
 (Azure DI OCR)        (GET/POST API)           (XLSX merge)

									  ^
									  |
							  +-----+------+
							  |   ai       |
							  | template_  |
							  | processor  |
							  +------------+
							  (Azure OpenAI/OpenAI)

									  ^
									  |
							  +-----+------+
							  |   auth     |
							  |  tokens    |
							  +------------+
							  (ENCODED_STRING → token)

									  ^
									  |
							+-------+--------+
							| Legacy Orchestrator |
							| pdf_processor_new    |
							| prompt.py (classes)  |
							+----------------------+
```

Notes:
- The wrappers import class implementations from the legacy file via a robust loader (`mtr_processor/utils/loader.py`).
- We can migrate those implementations into the package to remove the legacy file entirely.

## Typical workflow

1) Fill `.env` with Azure DI keys and `encoded_string`.
2) Run the HeatNumber flow to produce JSON in `output/`:
	- `python -m cli.process_heat <HEAT_NUMBER>`
3) Optionally upload JSONs:
	- `python -m cli.post_mtr_data` or `python post_mtr_data.py`

## Troubleshooting

- Invalid API response format: we print status and a short body preview and save the full body to `debug/`. Common causes: expired token, cert mismatch, or changed response schema.
- Missing Azure credentials: set `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` in `.env`.
- AI output not valid JSON: the tool attempts to extract JSON. If it fails, you can edit the JSON and re-run the XLSX update flow.

## Developer notes

- Main orchestrator implementations currently live in `pdf_processor_new prompt.py` and are imported by wrappers.
- Uploader class (`MTRDataPoster`) currently lives in `post_mtr_data.py` and is used by `cli/post_mtr_data.py`.
- Token helpers: `mtr_processor/auth/tokens.py` wraps `decryption.py`.
- Tests: `TESTS/`.

Future: move orchestrator and uploader implementations fully into `mtr_processor/` so legacy files can be deleted; add env overrides for certificate path/password.
