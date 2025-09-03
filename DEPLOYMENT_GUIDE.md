# Streamlit Cloud Deployment Guide

## Method 1: Streamlit Community Cloud

1. **Push your code to GitHub** (already done for this repo)

2. **Deploy on Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Connect your GitHub account
   - Select repository: `Unigalactix/GasOps-DI-JSON`
   - Main file path: `app_ocr.py`

3. **Configure Secrets:**
   - In Streamlit Cloud dashboard, go to your app settings
   - Click "Secrets" 
   - Add your credentials in TOML format:

```toml
[secrets]
AZURE_DI_ENDPOINT = "https://your-resource-name.cognitiveservices.azure.com/"
AZURE_DI_KEY = "your_32_character_api_key_here"
AZURE_DI_MODEL_ID = "prebuilt-layout"
AZURE_DI_API_VERSION = "2023-07-31"

# Optional: Add AI credentials
# AZURE_OPENAI_ENDPOINT = "https://your-openai-resource.openai.azure.com/"
# AZURE_OPENAI_KEY = "your_openai_key_here"
# AZURE_OPENAI_DEPLOYMENT = "your_deployment_name"
```

## Method 2: Docker Deployment

1. **Create Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app_ocr.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

2. **Deploy with environment variables:**

```bash
# Docker run with environment variables
docker run -p 8501:8501 \
  -e AZURE_DI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/" \
  -e AZURE_DI_KEY="your_api_key" \
  your-app-name
```

## Method 3: Other Cloud Platforms

### Heroku
Add config vars in Heroku dashboard or via CLI:
```bash
heroku config:set AZURE_DI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/"
heroku config:set AZURE_DI_KEY="your_api_key"
```

### Azure Container Apps
Set environment variables in container configuration:
```yaml
env:
  - name: AZURE_DI_ENDPOINT
    value: "https://your-resource.cognitiveservices.azure.com/"
  - name: AZURE_DI_KEY
    secretRef: azure-di-key
```

### AWS/Google Cloud
Use their respective secret management services and inject as environment variables.
