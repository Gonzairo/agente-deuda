from dotenv import load_dotenv
import os

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER      = os.getenv("TWILIO_NUMBER")
SUPABASE_URL       = os.getenv("SUPABASE_URL")
SUPABASE_KEY       = os.getenv("SUPABASE_KEY")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
MARGEN_MAX_PCT     = float(os.getenv("MARGEN_MAX_PCT", "0.35"))
MODEL              = os.getenv("MODEL", "claude-haiku-4-5-20251001")