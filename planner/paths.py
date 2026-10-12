from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "rensheng"
INDEX_DIR = ROOT / "data" / "index"
INDEX_PATH = INDEX_DIR / "segments.jsonl"
CONTEXT_DIR = ROOT / "data" / "context"
SESSIONS_DIR = ROOT / "data" / "sessions"
CHATS_DIR = ROOT / "data" / "chats"
MODELS_DIR = ROOT / "models"
ENTRIES_PATH = Path(__file__).resolve().parent / "entries.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
