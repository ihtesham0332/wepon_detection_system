import os
import cv2
import time
import queue
import logging
import threading
from datetime import datetime
from flask import Flask, Response, request, jsonify, render_template
from werkzeug.utils import secure_filename

import config
from detector import RealTimeDetector

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FlaskServer")

# Create Flask Application
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['UPLOAD_FOLDER'] = os.path.join(config.BASE_DIR, "uploads")
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max limit
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global Video Manager
class VideoManager:
    def __init__(self):
        self.cap = None
        self.active_source = "none" # "webcam", "file", "none"
        self.source_path = None
        self.running = False
        self.thread = None
        self.video_writer = None
        self.processed_url = None
        
        # Threat detector
        self.detector = RealTimeDetector()
        
        # Thread communication
        self.frame_lock = threading.Lock()
        self.current_frame = None  # Holds raw frame
        self.latest_encoded_frame = None  # Holds JPEG bytes
        
        # Event subscription for real-time alerts (SSE)
        self.listeners_lock = threading.Lock()
        self.listeners = [] # List of queue.Queue
        
        # Alert history (in-memory cache for quick page reloads)
        self.alert_history = []

    def register_listener(self):
        """Register a new client queue for receiving real-time alerts."""
        q = queue.Queue(maxsize=100)
        with self.listeners_lock:
            self.listeners.append(q)
        return q

    def unregister_listener(self, q):
        """Unregister client queue on disconnect."""
        with self.listeners_lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def _broadcast_alert(self, alert_data):
        """Send alert data to all active SSE client queues."""
        with self.listeners_lock:
            for listener in self.listeners:
                try:
                    listener.put_nowait(alert_data)
                except queue.Full:
                    # Clear out old item to make space
                    try:
                        listener.get_nowait()
                        listener.put_nowait(alert_data)
                    except Exception:
                        pass

    def start(self, source_type, path=None):
        """Stop any active stream and start the new capture thread."""
        self.stop()
        
        with self.frame_lock:
            self.running = True
            self.active_source = source_type
            self.source_path = path
            
        if source_type == "webcam":
            # On Windows, cv2.CAP_DSHOW is faster and avoids delay opening camera
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                # Fallback to default backend if DSHOW fails
                self.cap = cv2.VideoCapture(0)
            logger.info("Starting live webcam stream...")
        else:
            self.cap = cv2.VideoCapture(path)
            logger.info(f"Starting video file stream: {path}")

        if not self.cap.isOpened():
            logger.error(f"Failed to open video source: {source_type} (Path: {path})")
            self.active_source = "none"
            self.running = False
            return False

        # Initialize VideoWriter if active source is a file
        self.video_writer = None
        self.processed_url = None
        if source_type == "file":
            try:
                os.makedirs(config.PROCESSED_DIR, exist_ok=True)
                original_filename = os.path.basename(path)
                safe_filename = "processed_" + secure_filename(original_filename)
                output_path = os.path.join(config.PROCESSED_DIR, safe_filename)
                
                # Get video settings
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                file_fps = self.cap.get(cv2.CAP_PROP_FPS)
                fps_writer = file_fps if file_fps > 0 else 30.0
                
                # Codec config (using H.264 compatible mp4v container)
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                self.video_writer = cv2.VideoWriter(output_path, fourcc, fps_writer, (width, height))
                self.processed_url = f"/static/processed/{safe_filename}"
                logger.info(f"Initialized VideoWriter for saving processed video at: {output_path}")
            except Exception as e:
                logger.error(f"Failed to initialize VideoWriter: {e}. Video saving disabled.")
                self.video_writer = None
                self.processed_url = None

        # Launch processing loop in background thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop the background loop and release resources."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
            
        with self.frame_lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.current_frame = None
            self.latest_encoded_frame = None
            self.active_source = "none"
            self.source_path = None
        logger.info("Video stream stopped.")

    def _run_loop(self):
        """Main processing thread loop."""
        fps = 30 # Default safety fallback
        delay = 1.0 / fps
        
        # Attempt to read video's actual FPS if it is a file
        if self.active_source == "file" and self.cap:
            file_fps = self.cap.get(cv2.CAP_PROP_FPS)
            if file_fps > 0:
                fps = file_fps
                delay = 1.0 / fps

        # Keep track of frame times for logging actual FPS
        frame_counter = 0
        start_time = time.time()
        actual_fps = 0.0

        while self.running:
            loop_start = time.time()
            
            if not self.cap:
                break
                
            ret, frame = self.cap.read()
            if not ret:
                if self.active_source == "file":
                    logger.info("Video file stream ended. Stopping monitoring.")
                else:
                    logger.warning("Failed to grab camera frame. Stopping stream.")
                break

            # 1. Process Frame using the Detector
            processed_frame, frame_alerts = self.detector.process_frame(frame)
            
            # Write to output video file if writer is active
            if self.video_writer:
                try:
                    self.video_writer.write(processed_frame)
                except Exception as e:
                    logger.error(f"Failed to write frame to VideoWriter: {e}")

            # 2. Broadcaster & Cache Alert Event data
            for alert in frame_alerts:
                # Add actual UI FPS info
                alert['fps'] = round(actual_fps, 1)
                
                # Check for critical/high to store in server history cache
                if alert['type'] in ['CRITICAL', 'HIGH']:
                    # Prevent duplicates in immediate history feed
                    if not self.alert_history or self.alert_history[0]['message'] != alert['message'] or (time.time() - self.detector.last_snapshot_time < 0.2):
                        self.alert_history.insert(0, alert)
                        if len(self.alert_history) > 100: # Max cache size
                            self.alert_history.pop()
                            
                self._broadcast_alert(alert)

            # 3. Store JPEG Encoded Frame for Streaming
            ret_encode, jpeg = cv2.imencode('.jpg', processed_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ret_encode:
                with self.frame_lock:
                    self.current_frame = processed_frame
                    self.latest_encoded_frame = jpeg.tobytes()

            # FPS calculation
            frame_counter += 1
            elapsed = time.time() - start_time
            if elapsed >= 1.0:
                actual_fps = frame_counter / elapsed
                frame_counter = 0
                start_time = time.time()

            # Dynamic pacing to match source video FPS
            elapsed_loop = time.time() - loop_start
            sleep_time = max(0.001, delay - elapsed_loop)
            time.sleep(sleep_time)

        # Clean-up state
        with self.frame_lock:
            self.active_source = "none"
            self.running = False

        # Release the writer
        if self.video_writer:
            try:
                self.video_writer.release()
                logger.info("Released VideoWriter. Processed video file saved successfully.")
            except Exception as e:
                logger.error(f"Failed to release VideoWriter: {e}")
            self.video_writer = None

        # Send stream ended event to listeners
        if self.processed_url:
            self._broadcast_alert({
                'type': 'STREAM_ENDED',
                'message': 'Video processing completed.',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'details': 'The video has reached the end. You can now download the processed video below.',
                'download_url': self.processed_url
            })
            self.processed_url = None

    def get_stream_frame(self):
        """Retrieve current encoded JPEG frame."""
        with self.frame_lock:
            return self.latest_encoded_frame

# Instantiate global manager
video_manager = VideoManager()

# --- WEB CONTROLLER ROUTES ---

@app.route('/')
def index():
    """Main Web dashboard page."""
    # Check if default video file exists
    default_exists = os.path.exists(config.DEFAULT_VIDEO_PATH)
    return render_template('index.html', 
                           default_video=config.DEFAULT_VIDEO_NAME,
                           default_exists=default_exists)

@app.route('/history')
def history_page():
    """Separate Threat History snapshot viewing page."""
    return render_template('history.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route. Returns MJPEG stream."""
    def generate():
        while True:
            # Check if manager is running
            if not video_manager.running:
                # Yield placeholder or blank frame if stopped
                time.sleep(0.2)
                continue
                
            frame = video_manager.get_stream_frame()
            if frame is None:
                time.sleep(0.03)
                continue
                
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/alerts_feed')
def alerts_feed():
    """Server-Sent Events (SSE) route to push threat alerts in real-time."""
    def event_stream():
        q = video_manager.register_listener()
        logger.info("Client connected to Alert SSE Stream.")
        try:
            # Send initial state
            yield f"data: {{\"type\": \"SYSTEM\", \"message\": \"Alert service connected.\", \"active_model\": \"{video_manager.detector.coco_model_name_loaded}\"}} \n\n"
            
            while True:
                try:
                    # Wait for alert items to show up in queue (timeout prevents hanging on shutdown)
                    alert_data = q.get(timeout=1.0)
                    import json
                    yield f"data: {json.dumps(alert_data)}\n\n"
                except queue.Empty:
                    # Send keep-alive ping
                    yield "data: {\"type\": \"PING\"}\n\n"
        except GeneratorExit:
            logger.info("Client disconnected from Alert SSE Stream.")
        finally:
            video_manager.unregister_listener(q)

    return Response(event_stream(), mimetype='text/event-stream')

# --- API CONTROL ENDPOINTS ---

@app.route('/api/control', methods=['POST'])
def control():
    """Controls the stream state (start_webcam, start_file, stop)."""
    data = request.json or {}
    action = data.get('action')
    
    if action == 'start_webcam':
        success = video_manager.start("webcam")
        if success:
            return jsonify({"status": "success", "message": "Webcam started successfully."})
        return jsonify({"status": "error", "message": "Failed to open webcam camera."}), 500
        
    elif action == 'start_file':
        video_type = data.get('type')
        if video_type == 'default':
            file_path = config.DEFAULT_VIDEO_PATH
        else:
            filename = data.get('filename')
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": f"Video file not found at {file_path}"}), 404
            
        success = video_manager.start("file", file_path)
        if success:
            return jsonify({"status": "success", "message": f"Processing video: {os.path.basename(file_path)}"})
        return jsonify({"status": "error", "message": "Failed to open video file."}), 500
        
    elif action == 'stop':
        video_manager.stop()
        return jsonify({"status": "success", "message": "Monitoring stopped."})
        
    return jsonify({"status": "error", "message": "Invalid control action."}), 400

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Uploads a video file to the server uploads folder."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part in the request."}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No file selected."}), 400
        
    if file:
        filename = secure_filename(file.filename)
        dest_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(dest_path)
        logger.info(f"Video uploaded successfully and saved to {dest_path}")
        return jsonify({
            "status": "success", 
            "message": f"File '{filename}' uploaded successfully.",
            "filename": filename
        })
        
    return jsonify({"status": "error", "message": "File upload failed."}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Updates YOLO detection parameters in real-time."""
    data = request.json or {}
    try:
        conf_person = float(data.get('conf_person', config.DEFAULT_CONF_PERSON))
        conf_bag = float(data.get('conf_bag', config.DEFAULT_CONF_BAG))
        conf_gun = float(data.get('conf_gun', config.DEFAULT_CONF_GUN))
        proximity = int(data.get('proximity', config.PROXIMITY_THRESHOLD))
        
        video_manager.detector.update_thresholds(conf_person, conf_bag, conf_gun, proximity)
        return jsonify({"status": "success", "message": "Settings updated successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to update settings: {str(e)}"}), 400

@app.route('/api/history', methods=['GET'])
def get_history():
    """Retrieves all stored threat alert snapshots with details."""
    try:
        alert_files = os.listdir(config.ALERTS_DIR)
        history = []
        for file in alert_files:
            if file.endswith('.jpg') and file.startswith('snapshot_'):
                # Format: snapshot_{type}_{timestamp}.jpg -> snapshot_critical_20260714_172530.jpg
                parts = file.split('_')
                if len(parts) >= 4:
                    alert_type = parts[1].upper()
                    date_str = parts[2]
                    time_str = parts[3].split('.')[0]
                    
                    # Parse timestamp format
                    try:
                        timestamp = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        timestamp = "Unknown"
                        
                    msg = "CRITICAL: Gun detected near a Person!" if alert_type == 'CRITICAL' else "HIGH ALERT: Gun detected in scene!"
                    
                    history.append({
                        "filename": file,
                        "type": alert_type,
                        "timestamp": timestamp,
                        "message": msg,
                        "snapshot": f"/static/alerts/{file}"
                    })
        # Sort history by filename (newest first)
        history.sort(key=lambda x: x['filename'], reverse=True)
        return jsonify({"status": "success", "history": history})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Checks overall state of the server engine."""
    state = {
        "active_source": video_manager.active_source,
        "running": video_manager.running,
        "coco_model": video_manager.detector.coco_model_name_loaded,
        "bag_model_loaded": video_manager.detector.bag_model_loaded,
        "gun_model_loaded": video_manager.detector.gun_model_loaded,
        "current_thresholds": {
            "conf_person": video_manager.detector.conf_person,
            "conf_bag": video_manager.detector.conf_bag,
            "conf_gun": video_manager.detector.conf_gun,
            "proximity_px": video_manager.detector.proximity_threshold
        }
    }
    return jsonify(state)

# Run standard Flask application
if __name__ == '__main__':
    logger.info("Initializing Object Detection Application Server...")
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.DEBUG_MODE)
