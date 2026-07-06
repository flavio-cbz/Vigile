import sys
sys.path.append('z:/home/flavio/Docker-Compose/vigile')
from dotenv import load_dotenv
load_dotenv('z:/home/flavio/Docker-Compose/vigile/.env')

from master.config import settings
from master.core.security_manager import SecurityManager

sm = SecurityManager(settings.server_secret_key, settings.jwt_secret_key)
token, _ = sm.generate_join_token('test-worker', '', 'NetHunter-Worker', 'default')
print("NEW_TOKEN=" + token)
