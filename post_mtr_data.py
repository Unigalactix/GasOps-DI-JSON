#!/usr/bin/env python3
"""
MTR Data POST Script - Standalone JSON to Database Uploader
Reads JSON files from Sample json folder and posts them to the database using AddUpdateMTRMetadata API.

Usage: python post_mtr_data.py

Features:
- Standalone script (no dependencies on main processor)
- Batch processing of all JSON files in Sample json folder
- Certificate-based authentication with embedded API client
- Progress tracking and error reporting
- Heat number validation and duplicate handling
"""

import os
import sys
import json
import glob
import base64
import tempfile
import requests
import urllib3
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from pathlib import Path
from decryption import auth_token

# Add requests_pkcs12 for certificate authentication
try:
    import requests_pkcs12
    REQUESTS_PKCS12_AVAILABLE = True
except ImportError:
    print("❌ Error: requests_pkcs12 is required for API posting.")
    print("Install with: pip install requests_pkcs12")
    sys.exit(1)

def _get_logger() -> logging.Logger:
    """Create or return a rotating file logger for this script."""
    logger = logging.getLogger("mtr_poster")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "post_mtr_data.log")

    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_fmt = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_fmt)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger


LOGGER = _get_logger()

# Default authentication token - Updated token
encoded_string = os.getenv("encoded_string")
DEFAULT_AUTH_TOKEN = auth_token(encoded_string)

# SSL Configuration Options:
# 1. ENABLE_SSL_VERIFICATION = True (Recommended): Verifies SSL certificates for security
# 2. ENABLE_SSL_VERIFICATION = False + SUPPRESS_SSL_WARNINGS = True: Disables verification and warnings
# 3. ENABLE_SSL_VERIFICATION = False + SUPPRESS_SSL_WARNINGS = False: Shows warnings but no verification

class MTRDataPoster:
    """Standalone class for posting MTR JSON data to database via API."""
    
    # SSL Configuration
    ENABLE_SSL_VERIFICATION = True  # Set to False to disable SSL verification
    SUPPRESS_SSL_WARNINGS = False   # Set to True to suppress SSL warnings when verification is disabled
    
    def __init__(self, auth_token: str = None, certificate_path: str = "./certificate/oamsapicert2023.pfx"):
        """
        Initialize the MTR Data Poster.
        
        Args:
            auth_token: Authentication token for API access
            certificate_path: Path to the .pfx certificate file
        """
        self.auth_token = auth_token or DEFAULT_AUTH_TOKEN
        self.certificate_path = certificate_path
        self.certificate_password = "password1234"
        self.api_base_url = "https://oamsapi.gasopsiq.com"
        self.api_endpoint = "/api/AIMTRMetaData/AddUpdateMTRMetadata"
        
        # Validate certificate exists
        if not os.path.exists(self.certificate_path):
            raise FileNotFoundError(f"Certificate file not found: {self.certificate_path}")
        
        # Configure SSL warnings
        if not self.ENABLE_SSL_VERIFICATION and self.SUPPRESS_SSL_WARNINGS:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        print(f"🔐 Initialized MTR Data Poster")
        print(f"📜 Certificate: {self.certificate_path}")
        print(f"🔑 Auth token: {self.auth_token[:20]}...")
        print(f"🔒 SSL Verification: {'Enabled' if self.ENABLE_SSL_VERIFICATION else 'Disabled'}")
        LOGGER.info("Initialized MTR Data Poster")
        LOGGER.info("Certificate: %s", self.certificate_path)
        LOGGER.info("SSL Verification: %s", "Enabled" if self.ENABLE_SSL_VERIFICATION else "Disabled")
    
    def post_mtr_data(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post MTR data to the database using AddUpdateMTRMetadata API.
        
        Args:
            json_data: MTR data dictionary to post
            
        Returns:
            API response dictionary
        """
        url = f"{self.api_base_url}{self.api_endpoint}"
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "auth-token": self.auth_token
        }
        
        temp_file = None
        try:
            LOGGER.info("Posting HeatNumber=%s to %s", json_data.get("HeatNumber", "Unknown"), url)
            # Load certificate
            if not os.path.isfile(self.certificate_path):
                try:
                    cert_bytes = base64.b64decode(self.certificate_path)
                except Exception as decode_err:
                    LOGGER.exception("Failed to decode base64 certificate")
                    return {"success": False, "error": f"Failed to decode base64 certificate: {decode_err}"}
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pfx")
                temp_file.write(cert_bytes)
                temp_file.close()
                pfx_path = temp_file.name
            else:
                pfx_path = self.certificate_path
            
            with open(pfx_path, "rb") as f:
                pfx_data = f.read()
            
            # Make POST request
            response = requests_pkcs12.post(
                url,
                headers=headers,
                json=json_data,  # Use json parameter for POST body
                pkcs12_data=pfx_data,
                pkcs12_password=self.certificate_password,
                verify=self.ENABLE_SSL_VERIFICATION,  # Use class SSL configuration
                timeout=30
            )
            
            # Process response
            try:
                result = response.json()
                LOGGER.info("POST status=%s heat=%s", response.status_code, json_data.get("HeatNumber", "Unknown"))
                return {
                    "success": True, 
                    "data": result, 
                    "status_code": response.status_code,
                    "heat_number": json_data.get("HeatNumber", "Unknown")
                }
            except Exception:
                LOGGER.info("POST (non-JSON) status=%s heat=%s", response.status_code, json_data.get("HeatNumber", "Unknown"))
                return {
                    "success": True, 
                    "data": response.text, 
                    "status_code": response.status_code,
                    "heat_number": json_data.get("HeatNumber", "Unknown")
                }
        
        except Exception as e:
            LOGGER.exception("POST failed for heat=%s", json_data.get("HeatNumber", "Unknown"))
            return {
                "success": False, 
                "error": str(e),
                "heat_number": json_data.get("HeatNumber", "Unknown")
            }
        finally:
            if temp_file:
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass
    
    def find_json_files(self, folder_path: str) -> List[str]:
        """
        Find all JSON files in the specified folder.
        
        Args:
            folder_path: Path to the folder containing JSON files
            
        Returns:
            List of JSON file paths
        """
        json_pattern = os.path.join(folder_path, "*.json")
        json_files = glob.glob(json_pattern)
        
        if not json_files:
            print(f"⚠️  No JSON files found in: {folder_path}")
            LOGGER.warning("No JSON files found in: %s", folder_path)
            return []
        
        print(f"📁 Found {len(json_files)} JSON files in: {folder_path}")
        LOGGER.info("Found %d JSON files in: %s", len(json_files), folder_path)
        for file_path in sorted(json_files):
            print(f"   📄 {os.path.basename(file_path)}")
            LOGGER.info("Discovered file: %s", os.path.basename(file_path))
        
        return sorted(json_files)
    
    def load_json_file(self, file_path: str) -> Tuple[Dict[str, Any], str]:
        """
        Load and validate JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Tuple of (json_data, heat_number)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Extract heat number for identification
            heat_number = json_data.get("HeatNumber", "Unknown")
            
            return json_data, heat_number
        
        except Exception as e:
            raise Exception(f"Failed to load JSON file {file_path}: {e}")
    
    def validate_json_data(self, json_data: Dict[str, Any], file_path: str) -> bool:
        """
        Validate JSON data before posting.
        
        Args:
            json_data: JSON data to validate
            file_path: Path to the JSON file (for error reporting)
            
        Returns:
            True if valid, False otherwise
        """
        # Basic validation checks
        required_fields = ["HeatNumber"]
        
        for field in required_fields:
            if field not in json_data:
                print(f"❌ Validation failed for {os.path.basename(file_path)}: Missing required field '{field}'")
                LOGGER.error("Validation failed for %s: Missing required field '%s'", os.path.basename(file_path), field)
                return False
        
        heat_number = json_data.get("HeatNumber")
        if not heat_number or not str(heat_number).strip():
            print(f"❌ Validation failed for {os.path.basename(file_path)}: Empty HeatNumber")
            LOGGER.error("Validation failed for %s: Empty HeatNumber", os.path.basename(file_path))
            return False
        
        return True
    
    def process_json_files(self, folder_path: str) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """
        Process all JSON files in the folder and post them to the database.
        
        Args:
            folder_path: Path to the folder containing JSON files
            
        Returns:
            Tuple of (successful_posts, failed_posts)
        """
        json_files = self.find_json_files(folder_path)
        
        if not json_files:
            return [], []
        
        successful_posts = []
        failed_posts = []

        print(f"\n🚀 Starting batch POST operation...")
        LOGGER.info("Starting batch POST operation: %d files", len(json_files))
        print(f"📊 Processing {len(json_files)} JSON files...")
        print("=" * 60)
        
        for i, file_path in enumerate(json_files, 1):
            file_name = os.path.basename(file_path)
            print(f"\n📄 Processing {i}/{len(json_files)}: {file_name}")
            LOGGER.info("Processing file %d/%d: %s", i, len(json_files), file_name)
            
            try:
                # Load JSON file
                json_data, heat_number = self.load_json_file(file_path)
                print(f"   🔢 Heat Number: {heat_number}")
                LOGGER.info("Heat Number: %s", heat_number)
                
                # Validate JSON data
                if not self.validate_json_data(json_data, file_path):
                    failed_posts.append((heat_number, f"Validation failed for {file_name}"))
                    continue
                
                # Post to API
                print(f"   📤 Posting to database...")
                LOGGER.info("Posting heat %s to database", heat_number)
                result = self.post_mtr_data(json_data)
                
                if result.get("success"):
                    if result.get("status_code") == 200:
                        successful_posts.append((heat_number, file_name))
                        print(f"   ✅ Success: Posted {heat_number} to database")
                        LOGGER.info("Success: Posted %s", heat_number)
                        
                        # Log API response if verbose
                        api_data = result.get("data", {})
                        if isinstance(api_data, dict) and api_data:
                            print(f"   📋 API Response: {str(api_data)[:100]}...")
                            LOGGER.info("API Response (truncated): %s", str(api_data)[:200])
                    else:
                        failed_posts.append((heat_number, f"HTTP {result.get('status_code')}: {result.get('data', 'Unknown error')}"))
                        print(f"   ❌ Failed: HTTP {result.get('status_code')} - {result.get('data', 'Unknown error')}")
                        LOGGER.error("Failed: HTTP %s - %s", result.get('status_code'), str(result.get('data', 'Unknown error'))[:200])
                else:
                    error_msg = result.get("error", "Unknown error")
                    failed_posts.append((heat_number, error_msg))
                    print(f"   ❌ Failed: {error_msg}")
                    LOGGER.error("Failed: %s", error_msg)
            
            except Exception as e:
                error_msg = f"Processing error: {str(e)}"
                failed_posts.append(("Unknown", error_msg))
                print(f"   ❌ Error: {error_msg}")
                LOGGER.exception("Processing error for file %s", file_name)
        
        return successful_posts, failed_posts
    
    def print_summary(self, successful_posts: List[Tuple[str, str]], failed_posts: List[Tuple[str, str]]):
        """
        Print summary of the batch POST operation.
        
        Args:
            successful_posts: List of successful posts (heat_number, file_name)
            failed_posts: List of failed posts (heat_number, error)
        """
        total_files = len(successful_posts) + len(failed_posts)
        
        print("\n" + "=" * 60)
        print("🎯 Batch POST Operation Complete!")
        print("=" * 60)
        print(f"📊 Total Files Processed: {total_files}")
        print(f"✅ Successfully Posted: {len(successful_posts)}")
        print(f"❌ Failed to Post: {len(failed_posts)}")
        LOGGER.info("Batch complete: total=%d success=%d failed=%d", total_files, len(successful_posts), len(failed_posts))
        
        if successful_posts:
            print(f"\n✅ Successful Posts:")
            for heat_number, file_name in successful_posts:
                print(f"   🔢 {heat_number} ← {file_name}")
                LOGGER.info("Successful: %s (%s)", heat_number, file_name)
        
        if failed_posts:
            print(f"\n❌ Failed Posts:")
            for heat_number, error in failed_posts:
                print(f"   🔢 {heat_number}: {error}")
                LOGGER.error("Failed: %s -> %s", heat_number, error)
        
        # Success rate
        if total_files > 0:
            success_rate = (len(successful_posts) / total_files) * 100
            print(f"\n📈 Success Rate: {success_rate:.1f}%")
            LOGGER.info("Success rate: %.1f%%", success_rate)
        
        print("=" * 60)


def main():
    """Main entry point for the MTR Data Poster script."""
    print("MTR Data POST Script - JSON to Database Uploader")
    print("Reads JSON files and posts them to database via AddUpdateMTRMetadata API")
    print("=" * 70)
    LOGGER.info("Launcher started")
    
    try:
        # Initialize the poster
        poster = MTRDataPoster()
        # Determine default output folder path (where extracted JSONs are saved)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sample_json_folder = os.path.join(script_dir, "output")
        LOGGER.info("Using JSON folder: %s", sample_json_folder)

        # Ensure folder exists and guide user if empty
        if not os.path.exists(sample_json_folder):
            os.makedirs(sample_json_folder, exist_ok=True)
            print(f"📁 Created output folder: {sample_json_folder}")
            LOGGER.info("Created output folder: %s", sample_json_folder)
            print("💡 Place your JSON files in this folder and run again.")
            input("\nPress Enter to exit...")
            return

        print(f"📁 JSON Folder: {sample_json_folder}")
        
        # Interactive mode
        while True:
            print(f"\nSelect an option:")
            print("1. Process all JSON files in output folder")
            print("2. Process a specific JSON file")
            print("3. List JSON files in output folder")
            print("4. Test API connection")
            print("5. Exit")
            
            choice = input("\nEnter your choice (1-5): ").strip()
            LOGGER.info("Menu choice: %s", choice)
            
            if choice == "1":
                # Process all JSON files
                print(f"\n🔍 Scanning output folder...")
                successful_posts, failed_posts = poster.process_json_files(sample_json_folder)
                poster.print_summary(successful_posts, failed_posts)
            
            elif choice == "2":
                # Process specific file
                json_files = poster.find_json_files(sample_json_folder)
                if not json_files:
                    print("No JSON files found to process.")
                    continue
                
                print("\nAvailable JSON files:")
                for i, file_path in enumerate(json_files, 1):
                    print(f"   {i}. {os.path.basename(file_path)}")
                
                try:
                    file_index = int(input(f"\nSelect file (1-{len(json_files)}): ")) - 1
                    if 0 <= file_index < len(json_files):
                        selected_file = json_files[file_index]
                        print(f"\n📄 Processing: {os.path.basename(selected_file)}")
                        LOGGER.info("Selected file index=%d name=%s", file_index + 1, os.path.basename(selected_file))
                        
                        # Process single file
                        successful_posts, failed_posts = poster.process_json_files(os.path.dirname(selected_file))
                        # Filter results for selected file only
                        file_name = os.path.basename(selected_file)
                        successful_posts = [(h, f) for h, f in successful_posts if f == file_name]
                        failed_posts = [(h, e) for h, e in failed_posts if file_name in e]
                        
                        poster.print_summary(successful_posts, failed_posts)
                    else:
                        print("Invalid selection.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
            
            elif choice == "3":
                # List JSON files
                json_files = poster.find_json_files(sample_json_folder)
                if json_files:
                    print(f"\n📋 JSON Files in output folder:")
                    for i, file_path in enumerate(json_files, 1):
                        file_size = os.path.getsize(file_path)
                        file_size_kb = file_size / 1024
                        print(f"   {i}. {os.path.basename(file_path)} ({file_size_kb:.1f} KB)")
                        
                        # Try to extract heat number
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            heat_number = data.get("HeatNumber", "Unknown")
                            print(f"      🔢 Heat Number: {heat_number}")
                        except Exception:
                            print(f"      ❌ Could not read heat number")
                else:
                    print("No JSON files found.")
            
            elif choice == "4":
                # Test API connection
                print(f"\n🔍 Testing API connection...")
                print(f"🔗 URL: {poster.api_base_url}{poster.api_endpoint}")
                
                # Create a minimal test payload
                test_data = {
                    "HeatNumber": "TEST_CONNECTION",
                    "CertificationDate": datetime.now().strftime("%m/%d/%Y"),
                    "CompanyMTRFileID": 999999
                }
                
                result = poster.post_mtr_data(test_data)
                if result.get("success"):
                    print(f"✅ API connection successful!")
                    print(f"📊 Status Code: {result.get('status_code')}")
                    print(f"📋 Response: {str(result.get('data', ''))[:200]}...")
                    LOGGER.info("API connection test success: status=%s", result.get('status_code'))
                else:
                    print(f"❌ API connection failed!")
                    print(f"📋 Error: {result.get('error')}")
                    LOGGER.error("API connection test failed: %s", result.get('error'))
            
            elif choice == "5":
                print("\nGoodbye! 👋")
                break
            
            else:
                print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")
    
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        LOGGER.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        LOGGER.exception("Fatal error in launcher")
        input("\nPress Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()