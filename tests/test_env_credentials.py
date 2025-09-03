import os
from dotenv import load_dotenv, find_dotenv


def test_env_file_exists():
    env_path = find_dotenv()
    assert env_path, f"No .env file found in project root. Create one with AZURE_DI_ENDPOINT and AZURE_DI_KEY"


def test_required_vars_present():
    load_dotenv()
    endpoint = os.getenv('AZURE_DI_ENDPOINT') or os.getenv('AZURE_FORM_RECOGNIZER_ENDPOINT')
    key = os.getenv('AZURE_DI_KEY') or os.getenv('AZURE_FORM_RECOGNIZER_KEY')

    assert endpoint, "AZURE_DI_ENDPOINT or AZURE_FORM_RECOGNIZER_ENDPOINT is missing in .env"
    assert key, "AZURE_DI_KEY or AZURE_FORM_RECOGNIZER_KEY is missing in .env"


def test_endpoint_format():
    load_dotenv()
    endpoint = os.getenv('AZURE_DI_ENDPOINT') or os.getenv('AZURE_FORM_RECOGNIZER_ENDPOINT')
    assert endpoint.startswith('http'), "Endpoint does not look like a valid URL"
