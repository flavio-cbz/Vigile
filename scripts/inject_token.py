import sqlite3
import uuid
import time
import sys
sys.path.append('.')
from master.core.security_manager import SecurityManager
from master.config import settings

node_id = '0b20015f-2321-4dc5-b3a5-1a610297a169'
sec = SecurityManager(settings.server_secret_key, settings.jwt_secret_key)

token, payload = sec.generate_join_token(node_id=node_id, ip_prefix="")
token_hash = sec.join_token_hash(token)

conn = sqlite3.connect('/app/data/vigile.db')
cursor = conn.cursor()

cursor.execute("UPDATE join_tokens SET consumed = 1, expires_at = ? WHERE node_id = ? AND consumed = 0", (time.time(), node_id))

token_id = str(uuid.uuid4())
cursor.execute(
    "INSERT INTO join_tokens (id, node_id, token_hash, payload_b64, consumed, expires_at, created_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
    (token_id, node_id, token_hash, token.split(".", 1)[1], payload["expires_at"], time.time())
)

conn.commit()
conn.close()

print("TOKEN:" + token)
