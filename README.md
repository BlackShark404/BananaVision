# 🍌 BananaVision

**Banana Classification & Spoilage Prediction System**

BananaVision is a full-stack system designed to classify bananas using computer vision (YOLO26) and predict spoilage using machine learning (Random Forest Regression) combined with environmental sensor data.

## 🛠️ Tech Stack

### Backend
* **Framework:** FastAPI (Python)
* **Computer Vision:** YOLO26 (Ultralytics) for banana detection and classification
* **Machine Learning:** Random Forest Regression (scikit-learn) for spoilage prediction
* **Real-time Communication:** WebSockets
* **Hardware Integration:** Camera stream management and sensor data aggregation

### Frontend
* **Framework:** React 19 + TypeScript + Vite
* **Styling:** Tailwind CSS v4 + Shadcn UI
* **Charts/Visuals:** Recharts
* **Hardware Interaction:** `@zxing/browser` for barcode/QR scanning

## 🚀 Getting Started

The project comes with convenient development scripts to spin up both the frontend and backend simultaneously.

### Prerequisites
* Python 3.x
* Node.js (v18+ recommended)
* `npm`

### Running the App

**For macOS / Linux:**
```bash
./dev.sh
```

**For Windows:**
```cmd
dev.bat
```

The script will automatically:
1. Create a Python virtual environment and install backend dependencies (`requirements.txt`).
2. Install frontend `node_modules` (`npm install`).
3. Start the **FastAPI** backend on `http://localhost:8000`.
4. Start the **Vite** frontend on `http://localhost:5173`.

## 📂 Project Structure

* `/backend` - FastAPI Python application, containing ML models, camera services, and WebSocket handlers.
* `/frontend` - React application built with Vite and TailwindCSS.
* `/arduino` - Contains the sketch for the Arduino Uno handling the DHT22 temperature and humidity sensor.
* `/docs` - Additional documentation.

## 🌡️ Arduino Sensor Setup
The system uses an Arduino Uno connected via USB to send real-time temperature and humidity data using a DHT22 sensor.
1. Wire the **DHT22 Data Pin** to **Digital Pin 2** on the Arduino Uno.
2. Open `/arduino/dht22_sensor/dht22_sensor.ino` in the Arduino IDE.
3. Install the `DHT sensor library` by Adafruit via the Library Manager.
4. Upload the sketch to the Arduino Uno.
5. If necessary, update `sensor_serial_port` in `backend/.env` (default is `/dev/ttyUSB0` on Linux/Raspberry Pi or `COM3` on Windows).

## 📡 API Documentation
Once the backend is running, you can access the Swagger UI documentation at:
* [http://localhost:8000/docs](http://localhost:8000/docs)

## 👤 Login Credentials
For development purposes, the default login is:
* **Username:** `admin`
* **Password:** `admin`

## 🛑 Stopping the Servers
Simply press `Ctrl+C` in the terminal where you ran the dev script. It will cleanly shut down both the frontend and backend servers.
