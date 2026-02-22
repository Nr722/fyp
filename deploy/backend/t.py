from google import genai
from dotenv import load_dotenv
import os
load_dotenv()  # Load environment variables from .env file
key = os.getenv("GEMINI_API_KEY")
client = genai.Client()

print("List of models that support generateContent:\n")
for m in client.models.list():
    for action in m.supported_actions:
        if action == "generateContent":
            print(m.name)
