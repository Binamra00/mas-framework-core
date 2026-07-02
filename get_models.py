import requests

API_KEY = "YOUR_API_KEY_HERE"  # Paste your key, but don't paste it back to me!
URL = f"https://generativelanguage.googleapis.com/v1beta/models?key=AQ.Ab8RN6J8DM5BhaC1tEFJj_Tnh9-9BKEDECeUfXb9CASpY8HXxg"

print("Fetching available coding models for your API key...\n")
response = requests.get(URL)

if response.status_code != 200:
    print(f"Error: {response.status_code}\n{response.text}")
else:
    data = response.json()
    for model in data.get("models", []):
        # We only want models capable of text/code generation
        if "generateContent" in model.get("supportedGenerationMethods", []):
            name = model.get("name").replace("models/", "")
            print(f"Model ID: {name}")
            print(f" - Display: {model.get('displayName')}")
            print(f" - Tokens:  {model.get('inputTokenLimit')} Max Context")
            print("-" * 50)