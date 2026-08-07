"""
Sample application with intentional issues for Kutaar to detect.

Contains: security vulnerabilities, performance issues, architecture smells.
"""

import os
import pickle
import sqlite3
import hashlib
import subprocess

# SECURITY: Hardcoded credentials
DB_PASSWORD = "admin123"
API_KEY = "sk-1234567890abcdef"

# SECURITY: Weak hashing
def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

# SECURITY: SQL injection vulnerability
def get_user(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return cursor.execute(query).fetchall()

# SECURITY: Command injection
def ping_host(host):
    subprocess.call(f"ping -c 1 {host}", shell=True)

# SECURITY: Insecure deserialization
def load_data(filename):
    with open(filename, "rb") as f:
        return pickle.load(f)

# PERFORMANCE: O(n²) nested loop
def find_duplicates(items):
    duplicates = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates

# PERFORMANCE: String concatenation in loop
def build_report(rows):
    report = ""
    for row in rows:
        report += str(row) + "\n"
    return report

# PERFORMANCE: Reads entire file into memory
def count_lines(filename):
    with open(filename, "r") as f:
        return len(f.read().splitlines())

# ARCHITECTURE: God class — too many responsibilities
class UserManager:
    def create_user(self, data): pass
    def delete_user(self, id): pass
    def send_email(self, to, subject, body): pass
    def generate_report(self, format): pass
    def connect_to_db(self): pass
    def cache_user(self, user): pass
    def log_activity(self, action): pass
    def validate_input(self, data): pass
    def backup_database(self): pass
    def migrate_schema(self, version): pass

# ARCHITECTURE: Circular dependency potential
from sample_app.utils import format_date  # noqa: E402, F811

# DEVOPS: Hardcoded localhost
REDIS_URL = "localhost:6379"
DATABASE_URL = "localhost:5432"

# DEVOPS: Running as root implied
os.system("apt-get install python3")

# PERFORMANCE: Unnecessary copy
def process_data(data):
    copied = data.copy()
    result = []
    for item in copied:
        result.append(item * 2)
    return result
