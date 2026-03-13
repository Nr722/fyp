
import os
from dotenv import load_dotenv
import google.genai as genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Listing available models from Google GenAI API:")
for model in client.models.list():
    print(f"- {model.name} (DisplayName: {model.display_name})")
