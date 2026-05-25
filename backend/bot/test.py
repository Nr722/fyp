import os
from google import genai

client = genai.Client(api_key="AIzaSyCh-dPoCLOoZftYJFlVifUaZYW7Qcwz11c")

print("Available text generation models:")
for model in client.models.list():
    if "generateContent" in model.supported_actions:
        print(f"- {model.name}")