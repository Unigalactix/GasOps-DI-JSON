# Token Decryption and Authentication Module
# Handles base64 token decoding, credential extraction, and authentication token generation
# Provides secure token management for multi-tenant organization access

import base64
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
encoded_string = os.getenv("ENCODED_STRING")

def decode(encoded_string):
    """
    Decode a base64 encoded string.

    Args:
        encoded_string (str): The base64 encoded string to decode.

    Returns:
        dict: The decoded string stored in dictionary with the appropriate key value pairs.
    """
    # Decode the base64 string
    decoded_bytes = base64.b64decode(encoded_string)

    # Convert bytes to string
    decoded_string = decoded_bytes.decode('utf-8')

    decoded_items = decoded_string.split('&')    
    decoded_dict = {"LoginMasterID": decoded_items[0],
                  "Database_Name": decoded_items[1],
                  "OrgID": decoded_items[2]}
    print(decoded_dict.items())

    return decoded_dict

def generate_auth_token(login_master_id, database_name, org_id):
    """
    Generate authentication token for API calls
    
    Args:
        login_master_id (str): Login Master ID
        database_name (str): Database name
        org_id (str): Organization ID
        
    Returns:
        str: Base64 encoded authentication token
    """
    now_utc = datetime.now(timezone.utc)
    date_plus_one = (now_utc + timedelta(days=1)).isoformat()
    date_now = now_utc.isoformat()
    
    token_str = f"{date_plus_one}&{login_master_id}&{database_name}&{date_now}&{org_id}"
        
    return encode_base64(token_str)

def encode_base64(text: str) -> str:
    if text is None:
        return None
    text_bytes = text.encode('utf-8')
    return base64.b64encode(text_bytes).decode('utf-8')

def auth_token(encoded_string):
    # Initialize variables for credential extraction and token processing
    database_name = None  # Extracted from decoded token
    decrypted_fields = {}  # Decoded organization credentials
    auth_token = None  # Generated token for external API calls

    if encoded_string:
        try:
            decrypted_fields = decode(encoded_string)
            print(f"Successfully decoded credentials for org: {decrypted_fields.get('OrgID', 'unknown')}")
            database_name = decrypted_fields.get("Database_Name")
            
            # Generate authentication token for external API calls using decoded credentials
            # This token follows a specific format required by the weld management system APIs
            auth_token = generate_auth_token(
                decrypted_fields.get('LoginMasterID'),
                decrypted_fields.get('Database_Name'), 
                decrypted_fields.get('OrgID')
            )
            print("Generated authentication token for API calls", auth_token)
            # Expose as default token for CLI usage
            DEFAULT_AUTH_TOKEN = auth_token
                
        except Exception as e:
            print(f"Failed to decode token: {e}")
            raise HTTPException(status_code=400, detail="Invalid token")
        
        return DEFAULT_AUTH_TOKEN