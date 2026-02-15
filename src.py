import os
from dotenv import load_dotenv

load_dotenv()

IAM_TOKEN = os.getenv("IAM_TOKEN")
MODEL_URI = os.getenv("MODEL_URI")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
ENDPOINT = os.getenv("ENDPOINT")
