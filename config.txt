from dotenv import load_dotenv
import os

load_dotenv()

ODK_URL = os.getenv("ODK_URL")
ODK_USER = os.getenv("ODK_USER")
ODK_PASS = os.getenv("ODK_PASS")

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")