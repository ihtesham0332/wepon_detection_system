import sys
import os

def print_status(message, success=True):
    symbol = "[OK]" if success else "[FAIL]"
    print(f"{symbol} {message}")

print("====================================================")
print(" SENTRY VISION - ENVIRONMENT VERIFICATION SCRIPT")
print("====================================================")
print()

# 1. Check Python version
python_ver = sys.version_info
if python_ver.major == 3 and python_ver.minor >= 8:
    print_status(f"Python version: {sys.version} (Minimum 3.8 required)")
else:
    print_status(f"Python version: {sys.version}. Warning: Recommended Python version is 3.8+.", success=False)

# 2. Check Package Imports
modules = [
    ("flask", "Flask web server library"),
    ("cv2", "OpenCV computer vision library"),
    ("ultralytics", "YOLO model inference library"),
    ("huggingface_hub", "Hugging Face model downloader"),
    ("numpy", "Numerical computing library")
]

all_imported = True
for mod_name, desc in modules:
    try:
        mod = __import__(mod_name)
        ver = getattr(mod, "__version__", "Unknown Version")
        print_status(f"{mod_name} is installed. Version: {ver} ({desc})")
    except ImportError:
        print_status(f"{mod_name} is NOT installed! ({desc})", success=False)
        all_imported = False

if not all_imported:
    print()
    print("----------------------------------------------------")
    print("CRITICAL: Some required libraries are missing!")
    print("Please install them by running: pip install -r requirements.txt")
    print("----------------------------------------------------")
    sys.exit(1)

# 3. Test Detector instantiation & Model Downloading
print()
print("Testing Detector loading and pre-fetching weights...")
try:
    import config
    from detector import RealTimeDetector
    import numpy as np
    
    # Initialize detector (this will trigger downloading YOLOv12 and weapon models)
    print("Initializing RealTimeDetector (this may take a moment to download weights)...")
    detector = RealTimeDetector()
    
    # Test dummy frame inference
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    processed, alerts = detector.process_frame(dummy_frame)
    
    print_status("RealTimeDetector initialized and inference test completed successfully!")
    print_status(f"COCO Model loaded: {detector.coco_model_name_loaded}")
    print_status(f"Bag Model loaded: {detector.bag_model_loaded} (Path: {config.BAG_MODEL_PATH})")
    print_status(f"Gun Model loaded: {detector.gun_model_loaded} (Path: {config.GUN_MODEL_PATH})")
    
except Exception as e:
    print_status(f"Detector initialization failed: {e}", success=False)
    print()
    print("Troubleshooting details:")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("====================================================")
print(" VERIFICATION SUCCESSFUL: Your environment is ready!")
print(" Run 'run.bat' or 'python app.py' to launch the app.")
print("====================================================")
