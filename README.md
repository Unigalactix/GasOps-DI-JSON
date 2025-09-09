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

# Option 2: OpenAI
OPENAI_API_KEY=your_openai_api_key
```

## Usage

Simply run the application and follow the interactive prompts:

```bash
python pdf_processor.py
```

The application will:
1. Check your configuration
2. Ask for the PDF file path
# PDF Document Intelligence Processor

An interactive, easy-to-use application that converts PDF materials testing reports (MTRs) into structured JSON files. It's designed so a non-technical user can run PDFs through an OCR + AI pipeline and get consistent JSON output based on a template.

## What this repo contains
- `pdf_processor.py` — original script (interactive CLI).
- `pdf_processor_oop.py` — new object-oriented processor with clearer components.
- `Sample json/sample.json` — JSON template that AI will populate.
- `TESTS/` — small helper scripts and tests.

## High-level workflow (for non-technical users)
1. Prepare a PDF file (the MTR/certificate PDF you want to digitize).
2. Add credentials to a `.env` file (copy `.env.template` and fill keys).
3. Run the processor and enter the PDF path when asked.
4. The app will extract text (OCR), send it to the AI to map into the template, and save `{input_filename}.json` next to the PDF.

## Versions and environment (what was used to build & test)
- Python: 3.11 (the devcontainer uses Python 3.11 / Debian Bullseye image).
- Key packages (see `requirements.txt`):
  - python-dotenv — load `.env` files
  - requests — HTTP calls to Azure and OpenAI
  - openai — OpenAI client (optional)
  - pytest — lightweight testing utility

These packages are simple to install with `pip install -r requirements.txt`.

## Detailed, step-by-step guide (non-technical)

### 1) Create a `.env` file
1. Copy the `.env.template` file and rename it to `.env` in the project root.
2. Open `.env` in a text editor and paste your keys where shown:
	- For OCR (Azure Document Intelligence):
	  - `AZURE_DI_ENDPOINT` — e.g. `https://your-resource.cognitiveservices.azure.com/`
	  - `AZURE_DI_KEY` — the secret key for the resource
	- For AI (choose one):
	  - Azure OpenAI: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT`
	  - OR OpenAI: `OPENAI_API_KEY`

If you don't have these keys, contact the person or team that manages your Azure/OpenAI account — they will provide them.

### 2) Install Python dependencies (one-time)
Open a terminal (Windows PowerShell) and run:
```powershell
pip install -r requirements.txt
```

### 3) Run the processor (interactive)
You can use either the original script or the new object-oriented script. From the project folder run one of:
```powershell
# original CLI
python pdf_processor.py

# new, organized CLI (recommended)
python pdf_processor_oop.py
```

When prompted, enter the full path to the PDF file (or a URL if configured). Press Enter and follow prompts. If you choose default output, the JSON will be saved alongside the PDF with the same base name.

### 4) What the program does (simple terms)
- Step 1 — OCR: It sends the PDF to Azure's Document Intelligence and gets back the raw text and detected tables.
- Step 2 — AI mapping: It sends that text plus a blank template (sample.json) to an AI model which fills in the template fields with data found in the text.
- Step 3 — Save: The filled-in JSON is saved to disk.

## Where the output goes
- By default the JSON file is saved in the same folder as the input PDF with the same filename and `.json` extension.
- You can optionally specify a custom output file or directory in the prompts.

## Template (what the AI fills)
- The template file is `Sample json/sample.json`. It defines the fields (company, heat number, chemical composition, mechanical test results, etc.). The AI will fill those fields using values it finds in the PDF.

## Common questions (non-technical)

Q: What keys/credentials do I need and where do I get them?
A: You need:
- Azure Document Intelligence endpoint and key — provided by whoever manages your Azure subscriptions.
- Optionally, Azure OpenAI deployment credentials or an OpenAI API key for the AI step.

Q: Can I drag-and-drop a PDF into the app?
A: No. For now you type/paste the file path when prompted. The newer script supports entering multiple file paths for batch processing.

Q: What if the AI outputs incorrect values?
A: The AI does its best to map text into the template. If data is wrong, open the output JSON in a text editor and correct values manually. Keep a copy of the original PDF.

Q: Can I use an online URL instead of a local file?
A: The scripts expect local files by default. You can provide a URL in the newer OOP script if the helper to download URLs is enabled — ask me and I will add it.

## Troubleshooting (simple steps)

1. "The program says missing credentials":
	- Open `.env` and make sure `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` are present. If using AI, ensure either Azure OpenAI or OpenAI key is set.

2. "File not found":
	- Ensure you typed/pasted the correct full path to the PDF. On Windows, paths look like `C:\Users\You\Documents\file.pdf`.

3. "OCR or API errors (403, network)":
	- 403 means the key or resource is blocked. Check the Azure resource networking settings or confirm the key is correct.
	- Network errors may mean your machine cannot reach Azure; try again from a network that allows outbound requests.

4. "AI did not return valid JSON":
	- This can happen when the AI returns text around the JSON. The scripts try to extract valid JSON, but sometimes manual correction is necessary.

If you can't resolve an issue, copy the program output and share it with a technical person or me and I will help.

## Developer notes (brief, for maintainers)
- The repo contains two main entry points: `pdf_processor.py` (original) and `pdf_processor_oop.py` (refactored). The latter splits responsibilities into `DocumentIntelligenceOCR`, `AITemplateProcessor`, and `PDFProcessor` classes for easier testing and extension.
- Use `pytest` to run basic tests in `TESTS/`.

## Next steps / Improvements you can ask for
- Add URL-download support so you can paste HTTP links to PDFs.
- Add a simple GUI or drag-and-drop front-end.
- Add automatic validation rules for chemical and mechanical fields.
- Add CI tests and a GitHub Actions workflow.

---

If you'd like, I can now update the README to include screenshots or a short video note showing an example run; or I can add the one-click URL-download helper so you can paste links instead of local paths.
