import os

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Directory to store model weight files (.pt)
MODEL_DIR = os.path.join(BASE_DIR, "weights")
os.makedirs(MODEL_DIR, exist_ok=True)

# YOLO COCO Model Configurations (Standard YOLOv12 with fallbacks)
COCO_MODEL_NAME = os.path.join(BASE_DIR, "Human_Detection_Model.pt")
COCO_FALLBACK_MODELS = ["yolov12n.pt", "yolo11n.pt", "yolov8n.pt"]

# Gun Detection Model Configurations (HuggingFace repository source)
GUN_MODEL_REPO = "Subh775/Firearm_Detection_Yolov8n"
GUN_MODEL_FILENAME = "weights/best.pt"
GUN_MODEL_PATH = os.path.join(BASE_DIR, "Gun_Model.pt")

# Custom Bag Detection Model Configuration (User provided weights)
BAG_MODEL_PATH = os.path.join(BASE_DIR, "bag_model_train.pt")

# Directory to save alert snapshots of gun detections
ALERTS_DIR = os.path.join(BASE_DIR, "static", "alerts")
os.makedirs(ALERTS_DIR, exist_ok=True)

# Directory to save processed video downloads
PROCESSED_DIR = os.path.join(BASE_DIR, "static", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Default confidence thresholds (can be adjusted dynamically via Web UI)
DEFAULT_CONF_PERSON = 0.60
DEFAULT_CONF_BAG = 0.65
DEFAULT_CONF_GUN = 0.70

# Proximity threshold in pixels
# If a gun and person center coordinates are closer than this threshold, 
# it will trigger the "Person Carrying Gun" CRITICAL ALERT
PROXIMITY_THRESHOLD = 200

# Bounding Box and Label Text configurations for Video Processing
# Line thickness for bounding boxes and connection lines (default: 6, was: 4)
BOX_THICKNESS = 6
# Font scale for labels and overlay text (default: 1.2, was: 0.85)
FONT_SCALE = 1.2
# Font thickness for labels and overlay text (default: 3, was: 2)
FONT_THICKNESS = 3

# Default video file (will check if it exists in base dir)
DEFAULT_VIDEO_NAME = "WhatsApp Video 2026-07-14 at 16.55.08.mp4"
DEFAULT_VIDEO_PATH = os.path.join(BASE_DIR, DEFAULT_VIDEO_NAME)

# Flask application configurations
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5001
DEBUG_MODE = False

