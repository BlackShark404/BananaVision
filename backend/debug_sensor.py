import time
import requests
import argparse
import sys
import os
from datetime import datetime

# Add the app directory to path so we can import config if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.time import now_manila  # noqa: E402  (Asia/Manila clock)

try:
    from app.config import get_settings
    settings = get_settings()
except ImportError:
    settings = None

API_URL = "http://localhost:8000/api/v1/sensors/latest"

def monitor_api():
    print("=========================================")
    print("🍌 BananaVision - Sensor Debug (API Mode)")
    print("=========================================")
    print(f"Monitoring API: {API_URL}")
    print("Press Ctrl+C to exit.\n")
    
    # Authenticate to get a token
    auth_url = "http://localhost:8000/api/v1/auth/login"
    token = None
    headers = {}
    
    try:
        auth_resp = requests.post(auth_url, json={"username": "admin", "password": "admin"}, timeout=2)
        if auth_resp.status_code == 200:
            auth_data = auth_resp.json()
            if auth_data.get("status") == "success":
                token = auth_data["token"]["access_token"]
                headers["Authorization"] = f"Bearer {token}"
                print("✅ Successfully authenticated with API.")
            else:
                print(f"⚠️ Auth failed: {auth_data.get('reason', 'Unknown')}")
        else:
            print(f"⚠️ Auth endpoint returned HTTP {auth_resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Backend server is not running.")
        return
    except Exception as e:
        print(f"❌ Unexpected auth error: {e}")
        return
        
    if not token:
        print("❌ Could not obtain auth token. API requests will likely fail with 401.")

    while True:
        try:
            response = requests.get(API_URL, headers=headers, timeout=2)
            if response.status_code == 200:
                data = response.json()
                if data:
                    temp = data.get("temperature", "N/A")
                    hum = data.get("humidity", "N/A")
                    time_recorded = data.get("recorded_at", "N/A")
                    
                    if time_recorded != "N/A":
                        # Format timestamp nicely if possible
                        try:
                            dt = datetime.fromisoformat(time_recorded.replace('Z', '+00:00'))
                            time_recorded = dt.strftime('%H:%M:%S')
                        except ValueError:
                            pass
                            
                    print(f"✅ [{time_recorded}] Temp: {temp}°C | Humidity: {hum}%")
                else:
                    print("⚠️ No data received from API (sensor might be disconnected).")
            else:
                print(f"❌ API Error: HTTP {response.status_code} (Check token validity)")
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Backend server is not running.")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            
        time.sleep(2)

def monitor_serial(port, baudrate):
    print("=========================================")
    print("🍌 BananaVision - Sensor Debug (Serial Mode)")
    print("=========================================")
    print(f"Monitoring Port: {port} @ {baudrate} baud")
    print("Note: The backend server must NOT be running to use Serial mode, ")
    print("otherwise they will conflict over the port.")
    print("Press Ctrl+C to exit.\n")
    
    try:
        import serial
    except ImportError:
        print("❌ 'pyserial' is not installed. Run 'pip install pyserial'")
        sys.exit(1)
        
    try:
        ser = serial.Serial(port, baudrate, timeout=2)
        print(f"✅ Connected to {port}.")
    except Exception as e:
        print(f"❌ Failed to connect to {port}: {e}")
        sys.exit(1)
        
    while True:
        try:
            line = ser.readline().decode("utf-8").strip()
            if line:
                print(f"[{now_manila().strftime('%H:%M:%S')}] RAW: {line}")
            else:
                print(f"[{now_manila().strftime('%H:%M:%S')}] No data...")
        except Exception as e:
            print(f"❌ Serial read error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BananaVision Sensor Debugger")
    parser.add_argument("--serial", action="store_true", help="Read directly from the serial port instead of the backend API")
    parser.add_argument("--port", type=str, help="Serial port to use (overrides .env)")
    parser.add_argument("--baud", type=int, help="Baud rate to use (overrides .env)")
    
    args = parser.parse_args()
    
    if args.serial:
        port = args.port or (settings.sensor_serial_port if settings else "/dev/ttyUSB0")
        baud = args.baud or (settings.sensor_baud_rate if settings else 9600)
        monitor_serial(port, baud)
    else:
        monitor_api()
