import json
import os

CONFIG_FILE = "data/server_settings.json"
USER_DATA_FILE = "data/user_data.json"

def load_server_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_server_settings(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_user_data(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)