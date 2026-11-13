# Installation Guide

The following guide provides step-by-step installation instructions for BananaVision, an intelligent vision-based banana ripeness classification and post-harvest monitoring system. Ensure that all hardware components, inspection station peripherals, and software environment requirements are prepared before installation. The current version of BananaVision supports station deployment on Windows and Linux systems with web browser access across connected devices.

For publishing the dashboard from a Windows Mini PC over public HTTPS, use the dedicated [Windows Mini PC Deployment](windows-mini-pc-deployment.md) runbook after completing the station installation below.

### Inspection Station Hardware Installation

1. Assemble the inspection station frame and securely mount the camera mounting brackets, lighting enclosure, and fruit placement tray.

2. Mount the four USB webcams at the designated positions: Top (overhead, directly downward-facing), Left (lateral side), Right (lateral side), and Rear (inner concave and underside view).

3. Install the diffused LED lighting strip inside the enclosure to provide uniform, shadow-free illumination across the inspection surface.

4. Wire the DHT22 temperature and humidity sensor to the Arduino microcontroller power (5V and GND) and digital signal pins according to the pinout design.

5. Connect the four USB cameras directly into dedicated USB ports on the station computer, avoiding USB hubs to prevent video bandwidth contention.

6. Connect the Arduino microcontroller to the station computer using a USB serial cable.

7. Connect the Grozziie TP870 S thermal label printer to the station computer via USB and load the 40mm by 30mm thermal adhesive label roll.

8. Power on the station computer and peripherals, and verify that all cameras, the Arduino sensor module, and the label printer receive power successfully.

### Software and Environment Installation (Station Server)

1. Install Python 3.12, Node.js (version 20 or higher), Git, and PostgreSQL on the station computer.

2. Install the official Grozziie TP870 S printer driver on the host computer and set the default label stock size to 40mm wide by 30mm high in printing preferences.

3. Clone or extract the BananaVision project repository into the designated directory on the station drive.

4. Set up the Python virtual environment, activate it, and install all backend dependencies using pip from the requirements specification.

5. Place the trained YOLO object detection model weights (banana_yolov26n.pt) and the Random Forest spoilage regression weights (spoilage_rfr.joblib) in the backend model weights directory.

6. Configure the environment variables in the station configuration file, including the PostgreSQL database connection string, security secret keys, camera device indices, and serial sensor port.

### System Setup and Verification

1. Initialize the PostgreSQL database by running database migrations to create all required schema tables and default system settings.

2. Configure automatic kiosk startup by placing the station launcher shortcut in the operating system startup folder and enabling system auto-login.

3. Launch the BananaVision backend and frontend services, and verify that the API health check endpoint returns active status for all models, database, and sensor services.

4. Log in to the administrator portal, open Scanner Configuration, and use the camera calibration tool to verify that all four camera feeds (Top, Left, Right, and Rear) display clear, correctly oriented live images.

5. Perform a test scan with a sample banana bunch from the kiosk interface to confirm pre-detection gating, multi-camera classification, spoilage prediction, and test label printing.

