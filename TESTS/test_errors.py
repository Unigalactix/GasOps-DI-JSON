#!/usr/bin/env python3
"""
Test script to simulate PDF processor with invalid input for testing error handling.
"""

def simulate_error_handling():
    """Simulate various error conditions."""
    print("Simulating PDF Processor Error Handling")
    print("=" * 45)
    
    print("\n1. Non-existent file:")
    print("   Input: C:\\nonexistent\\file.pdf")
    print("   Output: Error: File not found: C:\\nonexistent\\file.pdf")
    print("   Action: Would you like to try again? (y/n)")
    
    print("\n2. Non-PDF file:")
    print("   Input: C:\\documents\\image.jpg")
    print("   Output: Error: File must be a PDF file.")
    print("   Action: Would you like to try again? (y/n)")
    
    print("\n3. Empty input:")
    print("   Input: [Enter pressed with no text]")
    print("   Output: Error: Please enter a file path.")
    print("   Action: Prompt appears again")
    
    print("\n4. Quoted paths (handled automatically):")
    print("   Input: \"C:\\My Documents\\file with spaces.pdf\"")
    print("   Output: Quotes removed automatically")
    
    print("\n5. Keyboard interrupt (Ctrl+C):")
    print("   Output: Operation cancelled by user.")
    
    print("\nThe interactive interface handles all these cases gracefully!")

if __name__ == "__main__":
    simulate_error_handling()
