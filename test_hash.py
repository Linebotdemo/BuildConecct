# test_hash.py
from auth import get_password_hash, verify_password

plain = "Suramudankui4"
hashed = get_password_hash(plain)
print("Generated Hash:", hashed)
print("Verification result:", verify_password(plain, hashed))
