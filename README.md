# 🍌 BananaVision

**Banana Classification & Spoilage Prediction System**

BananaVision is a full-stack system designed to classify bananas using computer vision (YOLOv8n) and predict spoilage using machine learning (Random Forest Regression) combined with environmental sensor data. 

## 🛠️ Tech Stack

### Backend
* **Framework:** FastAPI (Python)
* **Computer Vision:** YOLOv8n (Ultralytics) for banana detection and classification
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
* `/docs` - Additional documentation.

## 📡 API Documentation
Once the backend is running, you can access the Swagger UI documentation at:
* [http://localhost:8000/docs](http://localhost:8000/docs)

## 👤 Login Credentials
For development purposes, the default login is:
* **Username:** `admin`
* **Password:** `admin`

## 🛑 Stopping the Servers
Simply press `Ctrl+C` in the terminal where you ran the dev script. It will cleanly shut down both the frontend and backend servers.
