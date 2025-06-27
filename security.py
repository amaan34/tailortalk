import os
from cryptography.fernet import Fernet
import json

# Load the secret key from environment variables
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("No SECRET_KEY set for encryption")

f = Fernet(SECRET_KEY.encode())

def encrypt_token(token: dict) -> str:
    """Encrypts a token dictionary into a string."""
    token_json = json.dumps(token)
    encrypted_token = f.encrypt(token_json.encode())
    return encrypted_token.decode()

def decrypt_token(encrypted_token: str) -> dict:
    """Decrypts an encrypted token string back into a dictionary."""
    decrypted_token_json = f.decrypt(encrypted_token.encode())
    return json.loads(decrypted_token_json)