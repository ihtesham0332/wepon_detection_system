# Sentry Vision: Real-Time YOLOv12 Threat Detection

Sentry Vision is a web-based real-time video surveillance dashboard developed in Python, Flask, and OpenCV. It utilizes standard **YOLOv12** (with fallbacks to YOLO11/YOLOv8) and a specialized fine-tuned weapon detection model to process streams, identify **Persons, Bags, and Guns**, and trigger instant warnings.

The system features:
1. **Critical Warning Siren:** Plays a dual-frequency security alarm dynamically generated via the browser's HTML5 Web Audio API if a person appears with a gun.
2. **Visual Flashing Alerts:** Triggers red screen border flashes during critical detections and orange warnings during standalone weapon sightings.
3. **Responsive Glassmorphism Dashboard:** Dark mode layout with real-time logging, dynamic confidence threshold sliders, and active metric monitors (FPS, active model).
4. **Snapshot Archive:** Saves timestamped JPEG frames on gun detection and presents them in a visual history gallery with a lightbox zoom modal.

---

## Workspace Layout
```
d:\Girl Project\Project_Code/
│
├── app.py                      # Flask Server (streaming & SSE alerts API)
├── config.py                   # Central Configurations & Threshold Settings
├── detector.py                 # Core Detector (YOLOv12 inference & proximity logic)
├── requirements.txt            # Required Python packages
├── run.bat                     # Windows CLI startup script
├── verify_env.py               # Pre-flight environment check & pre-downloader
├── README.md                   # Installation & documentation manual
│
├── templates/
│   └── index.html              # Dashboard Web UI
│
├── static/
│   ├── css/
│   │   └── styles.css          # Glassmorphic styles
│   └── js/
│       └── main.js             # Frontend controllers & audio synthesizers
│
└── weights/                    # Pre-trained models (.pt weights)
```

---

## Installation & Setup

### Prerequisite
Make sure Python 3.8 or higher is installed. You can check your version in a command prompt:
```bash
python --version
```

### Step 1: Install Dependencies
Open a command prompt in the project folder and run:
```bash
pip install -r requirements.txt
```

### Step 2: Pre-Flight Check & Pre-Download (Highly Recommended)
To verify your environment is ready and to pre-download the models (YOLOv12 standard and specialized Gun Detection weights) so you don't wait on first run, execute:
```bash
python verify_env.py
```
*Note: This script will download `yolov12n.pt` and download/save the weapon model weights directly into the `weights/` folder.*

### Step 3: Run the Application
Double-click `run.bat` in Windows Explorer, or execute:
```bash
python app.py
```
Open your web browser and navigate to:
```
http://localhost:5001
```

---

## Key Features & How To Test

1. **Test with your Default Video:**
   The application automatically detects that you have `WhatsApp Video 2026-07-14 at 16.55.08.mp4` in the project root. Click the **"Test Default Video"** button in the dashboard to immediately stream it through the detector.
2. **Active Webcam Stream:**
   Click **"Active Webcam"** to capture frames from your default webcam.
3. **Upload custom videos:**
   Click **"Upload Custom Video"** to process custom security camera files.
4. **Interactive Parameters Panel:**
   Adjust detection sliders (Person Confidence, Bag Confidence, Gun Confidence, and Proximity pixels) in real-time. The server dynamically updates thresholds without restarting the stream.
5. **Real-time Alert feed & Lightbox:**
   When a gun is detected, a clickable alert row appears. Clicking it launches the Lightbox modal showing the exact snapshot when the threat occurred.

---

## Advanced Software Engineering Details

- **Model Fallback System:**
  During initialization, `detector.py` attempts to load `yolov12n.pt`. If the installed `ultralytics` package does not yet support YOLOv12, it catches the error and cascades down to `yolo11n.pt` and then `yolov8n.pt`.
- **Background Video Threading:**
  A dedicated background worker (`VideoManager` class in `app.py`) parses video frames asynchronously and pushes them into an encoded JPEG buffer. This decouples video decoding from the Flask web server, guaranteeing low-latency frames.
- **Server-Sent Events (SSE):**
  Instead of polling the server or setting up heavy WebSocket libraries (which can cause driver/async conflicts on Windows), the app uses a clean, native SSE stream (`/alerts_feed`) to push lightweight JSON threat events.
- **No-Audio-Loss Siren:**
  By synthesizing sound on the client-side utilizing the Web Audio API, we avoid importing heavy `.mp3` files, eliminating loading delays, and ensuring the alert sounds immediately on trigger.
