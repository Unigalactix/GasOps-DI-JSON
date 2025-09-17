#!/usr/bin/env python3
"""
Test multiple heat numbers to identify the issue
"""

import requests_pkcs12
import os

def test_heat_numbers():
    print("🔍 TESTING MULTIPLE HEAT NUMBERS")
    print("=" * 50)
    
    # Test different heat numbers
    test_heat_numbers = [
        "PC0314",      # Original failing one
        "123456",      # Generic test
        "TEST001",     # Test value
        "PP5BAN2MXH115OG0",  # From previous examples
        ""             # Empty value
    ]
    
    auth_token = "MSZDRURFTU9ORVcwMzE0JkNFREVNTyA="
    url = "https://oamsapi.gasopsiq.com/api/AIMTRMetaData/GetMTRFileDatabyHeatNumber"
    cert_path = "./certificate/oamsapicert2023.pfx"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json", 
        "auth-token": auth_token
    }
    
    # Load certificate
    with open(cert_path, "rb") as f:
        pfx_data = f.read()
    
    for heat_number in test_heat_numbers:
        print(f"\n📞 Testing Heat Number: '{heat_number}'")
        
        params = {"heatNumber": heat_number} if heat_number else {}
        
        try:
            response = requests_pkcs12.get(
                url,
                headers=headers,
                params=params,
                pkcs12_data=pfx_data,
                pkcs12_password="password1234",
                timeout=30,
                verify=False
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'Obj' in data:
                        obj_data = data['Obj']
                        if isinstance(obj_data, list) and len(obj_data) > 0:
                            print(f"   ✅ Success - Found {len(obj_data)} objects")
                            first_obj = obj_data[0]
                            if isinstance(first_obj, dict) and 'BinaryString' in first_obj:
                                binary_str = first_obj['BinaryString']
                                if binary_str:
                                    print(f"   ✅ BinaryString found (length: {len(binary_str)})")
                                else:
                                    print(f"   ❌ BinaryString is empty")
                            else:
                                print(f"   ❌ No BinaryString in object")
                        else:
                            print(f"   ❌ Empty or invalid Obj array")
                    else:
                        print(f"   ❌ No 'Obj' in response or invalid format")
                except Exception as e:
                    print(f"   ❌ JSON parse error: {e}")
                    print(f"   Raw response: {response.text[:200]}")
            else:
                print(f"   ❌ Error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Request failed: {e}")

if __name__ == "__main__":
    test_heat_numbers()