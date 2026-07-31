import os

os.environ.setdefault("ENV", "local")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
os.environ.setdefault("DB_NAME", "test_db")
