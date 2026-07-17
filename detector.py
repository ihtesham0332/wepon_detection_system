import os
import cv2
import time
import math
import logging
import threading
from datetime import datetime
from ultralytics import YOLO
import config

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RealTimeDetector")

class RealTimeDetector:
    def __init__(self):
        self.coco_model = None
        self.bag_model = None
        self.gun_model = None
        self.lock = threading.Lock()
        
        # UI Thresholds (can be adjusted dynamically)
        self.conf_person = config.DEFAULT_CONF_PERSON
        self.conf_bag = config.DEFAULT_CONF_BAG
        self.conf_gun = config.DEFAULT_CONF_GUN
        self.proximity_threshold = config.PROXIMITY_THRESHOLD
        
        # State tracking
        self.coco_model_name_loaded = ""
        self.bag_model_loaded = False
        self.gun_model_loaded = False
        self.last_snapshot_time = 0
        self.snapshot_cooldown = 5.0  # seconds between snapshots to prevent spamming
        
        # Caching for frame skipping
        self.frame_count = 0
        self.last_persons = []
        self.last_bags = []
        self.last_guns = []
        self.last_alerts = []
        self.last_critical = False
        self.last_high = False
        
        # Load models
        self._load_coco_model()
        self._load_bag_model()
        self._load_gun_model()

    def _load_coco_model(self):
        """Loads YOLOv12 for Person/Bag detection, with fallbacks to YOLO11 and YOLOv8."""
        models_to_try = [config.COCO_MODEL_NAME] + config.COCO_FALLBACK_MODELS
        for model_name in models_to_try:
            try:
                logger.info(f"Attempting to load COCO model: {model_name}...")
                # Ultralytics auto-downloads standard models if they don't exist locally
                self.coco_model = YOLO(model_name)
                self.coco_model_name_loaded = model_name
                logger.info(f"Successfully loaded COCO model: {model_name}")
                return
            except Exception as e:
                logger.warning(f"Could not load {model_name}: {e}. Trying next fallback...")
        
        logger.error("Failed to load any COCO YOLO models.")
        raise RuntimeError("No available COCO YOLO model could be loaded.")

    def _load_gun_model(self):
        """Loads or downloads the weapon detection model."""
        # 1. Check if model exists locally in the weights folder
        if os.path.exists(config.GUN_MODEL_PATH):
            try:
                logger.info(f"Loading local weapon detection model from {config.GUN_MODEL_PATH}...")
                self.gun_model = YOLO(config.GUN_MODEL_PATH)
                self.gun_model_loaded = True
                logger.info("Successfully loaded local gun detection model.")
                return
            except Exception as e:
                logger.error(f"Error loading local gun model: {e}. Re-downloading...")

        # 2. Try Hugging Face Hub download
        try:
            logger.info(f"Downloading weapon model '{config.GUN_MODEL_REPO}' via Hugging Face Hub...")
            from huggingface_hub import hf_hub_download
            import shutil
            
            downloaded_path = hf_hub_download(
                repo_id=config.GUN_MODEL_REPO, 
                filename=config.GUN_MODEL_FILENAME,
                cache_dir=os.path.join(config.MODEL_DIR, "cache")
            )
            shutil.copy(downloaded_path, config.GUN_MODEL_PATH)
            self.gun_model = YOLO(config.GUN_MODEL_PATH)
            self.gun_model_loaded = True
            logger.info("Successfully downloaded and loaded gun model via Hugging Face.")
            return
        except Exception as e:
            logger.warning(f"Hugging Face Hub download failed: {e}. Trying direct URL download...")

        # 3. Try direct HTTP download
        try:
            import urllib.request
            url = f"https://huggingface.co/{config.GUN_MODEL_REPO}/resolve/main/{config.GUN_MODEL_FILENAME}"
            logger.info(f"Downloading from direct URL: {url}...")
            urllib.request.urlretrieve(url, config.GUN_MODEL_PATH)
            
            self.gun_model = YOLO(config.GUN_MODEL_PATH)
            self.gun_model_loaded = True
            logger.info("Successfully downloaded and loaded gun model via direct URL.")
            return
        except Exception as e:
            logger.error(f"Direct download failed: {e}. Weapon detection will be offline.")
            self.gun_model = None
            self.gun_model_loaded = False

    def _load_bag_model(self):
        """Loads the custom trained bag detection model."""
        if os.path.exists(config.BAG_MODEL_PATH):
            try:
                logger.info(f"Loading custom bag detection model from {config.BAG_MODEL_PATH}...")
                self.bag_model = YOLO(config.BAG_MODEL_PATH)
                self.bag_model_loaded = True
                logger.info(f"Successfully loaded custom bag detection model. Classes: {self.bag_model.names}")
            except Exception as e:
                logger.error(f"Error loading custom bag model: {e}")
                self.bag_model_loaded = False
        else:
            logger.warning(f"Custom bag model not found at {config.BAG_MODEL_PATH}. Falling back to COCO for bag detection.")
            self.bag_model_loaded = False

    def update_thresholds(self, conf_person, conf_bag, conf_gun, proximity):
        """Updates the confidence and spatial thresholds dynamically from the Web UI."""
        with self.lock:
            self.conf_person = conf_person
            self.conf_bag = conf_bag
            self.conf_gun = conf_gun
            self.proximity_threshold = proximity
            logger.info(f"Updated thresholds: Person={self.conf_person}, Bag={self.conf_bag}, Gun={self.conf_gun}, Proximity={self.proximity_threshold}px")

    def process_frame(self, frame):
        """
        Processes a single frame:
        1. Detects Person and Bags using the COCO YOLO model.
        2. Detects Guns using the Weapon YOLO model.
        3. Analyzes spatial proximity between Persons and Guns.
        4. Draws custom bounding boxes and overlays alerts.
        5. Saves alert snapshot on critical detections with a cooldown.
        
        Returns:
            processed_frame (numpy.ndarray): Frame with bounding boxes and overlays.
            alerts (list): List of alert metadata dicts triggered in this frame.
        """
        if frame is None:
            return None, []

        with self.lock:
            conf_p = self.conf_person
            conf_b = self.conf_bag
            conf_g = self.conf_gun
            prox_thresh = self.proximity_threshold

        h, w = frame.shape[:2]
        
        # Increment frame counter for throttled diagnostics and frame skipping
        self.frame_count = getattr(self, 'frame_count', 0) + 1
        show_diagnostics = (self.frame_count % 30 == 0)
        
        # Run inference on frame 1 and every 3rd frame afterwards (skip factor = 3)
        run_inference = (self.frame_count == 1 or self.frame_count % 3 == 0)

        if run_inference:
            persons = []  # List of dicts: {'box': [x1, y1, x2, y2], 'conf': float, 'center': (cx, cy)}
            bags = []     # List of dicts: {'box': [x1, y1, x2, y2], 'conf': float, 'label': str}
            guns = []     # List of dicts: {'box': [x1, y1, x2, y2], 'conf': float, 'center': (cx, cy)}
            alerts = []
            critical_alert_triggered = False
            high_alert_triggered = False

            # 1. Run COCO YOLO Model (Person detection & fallback Bags)
            if self.coco_model:
                try:
                    coco_results = self.coco_model(frame, conf=0.1, verbose=False)[0]
                    
                    # Raw model logging for pre-filtering diagnostics
                    if show_diagnostics:
                        raw_dets = []
                        for box in coco_results.boxes:
                            cid = int(box.cls[0])
                            cname = self.coco_model.names.get(cid, str(cid))
                            ccnf = float(box.conf[0])
                            raw_dets.append(f"{cname}({ccnf:.2f})")
                        if raw_dets:
                            logger.info(f"[DIAGNOSTIC] Raw COCO Detections: {', '.join(raw_dets)}")

                    for box in coco_results.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        xyxy = box.xyxy[0].tolist() # [x1, y1, x2, y2]
                        
                        # Class 0: Person
                        if cls_id == 0 and conf >= conf_p:
                            cx = int((xyxy[0] + xyxy[2]) / 2)
                            cy = int((xyxy[1] + xyxy[3]) / 2)
                            persons.append({
                                'box': [int(c) for c in xyxy],
                                'conf': conf,
                                'center': (cx, cy)
                            })
                        
                        # Fallback Bag detection using COCO classes (only if custom bag model is not loaded)
                        elif not self.bag_model_loaded and cls_id in [24, 26, 28] and conf >= conf_b:
                            label_map = {24: "Backpack", 26: "Handbag", 28: "Suitcase"}
                            bags.append({
                                'box': [int(c) for c in xyxy],
                                'conf': conf,
                                'label': f"Bag ({label_map.get(cls_id, 'Bag')})"
                            })
                except Exception as e:
                    logger.error(f"Error running COCO YOLO model inference: {e}")

            # 1b. Run Custom Bag YOLO Model (if loaded)
            if self.bag_model_loaded and self.bag_model:
                try:
                    bag_results = self.bag_model(frame, conf=0.1, verbose=False)[0]
                    
                    # Raw model logging for pre-filtering diagnostics
                    if show_diagnostics:
                        raw_dets = []
                        for box in bag_results.boxes:
                            cid = int(box.cls[0])
                            cname = self.bag_model.names.get(cid, str(cid))
                            ccnf = float(box.conf[0])
                            raw_dets.append(f"custom_bag_{cname}({ccnf:.2f})")
                        if raw_dets:
                            logger.info(f"[DIAGNOSTIC] Raw Custom Bag Detections: {', '.join(raw_dets)}")

                    for box in bag_results.boxes:
                        cls_id = int(box.cls[0])
                        cname = self.bag_model.names.get(cls_id, str(cls_id)).lower()
                        conf = float(box.conf[0])
                        xyxy = box.xyxy[0].tolist()
                        
                        # Only accept if the class name is related to a bag (ignore person or other classes)
                        is_bag_class = "bag" in cname or "pack" in cname or "case" in cname
                        
                        if is_bag_class and conf >= conf_b:
                            # Format label name nicely (e.g., "Schoolbag" -> "School Bag")
                            friendly_label = self.bag_model.names.get(cls_id, "Bag")
                            if friendly_label.lower() == "schoolbag":
                                friendly_label = "School Bag"
                            elif friendly_label.lower() == "handbag":
                                friendly_label = "Handbag"
                                
                            bags.append({
                                'box': [int(c) for c in xyxy],
                                'conf': conf,
                                'label': friendly_label
                            })
                except Exception as e:
                    logger.error(f"Error running custom Bag model inference: {e}")

            # 2. Run Gun Model
            if self.gun_model_loaded and self.gun_model:
                try:
                    gun_results = self.gun_model(frame, conf=0.1, verbose=False)[0]
                    
                    # Raw model logging for pre-filtering diagnostics
                    if show_diagnostics:
                        raw_dets = []
                        for box in gun_results.boxes:
                            cid = int(box.cls[0])
                            cname = self.gun_model.names.get(cid, str(cid))
                            ccnf = float(box.conf[0])
                            raw_dets.append(f"{cname}({ccnf:.2f})")
                        if raw_dets:
                            logger.info(f"[DIAGNOSTIC] Raw Gun Detections: {', '.join(raw_dets)}")

                    for box in gun_results.boxes:
                        conf = float(box.conf[0])
                        xyxy = box.xyxy[0].tolist()
                        
                        # Class 0 is "Gun" in our firearm detection model
                        if conf >= conf_g:
                            cx = int((xyxy[0] + xyxy[2]) / 2)
                            cy = int((xyxy[1] + xyxy[3]) / 2)
                            guns.append({
                                'box': [int(c) for c in xyxy],
                                'conf': conf,
                                'center': (cx, cy)
                            })
                except Exception as e:
                    logger.error(f"Error running Gun model inference: {e}")

            # Console logging for debug help (throttled to when bags/guns are present)
            if len(bags) > 0 or len(guns) > 0:
                logger.info(f"Detections -> Persons: {len(persons)}, Bags: {len(bags)}, Guns: {len(guns)}")

            # 3. Analyze Spatial Proximity and Bounding Box Overlaps
            for p in persons:
                p_box = p['box']
                px1, py1, px2, py2 = p_box
                pcx, pcy = p['center']
                
                for g in guns:
                    g_box = g['box']
                    gx1, gy1, gx2, gy2 = g_box
                    gcx, gcy = g['center']
                    
                    # Check 1: Overlap
                    overlap_x = max(0, min(px2, gx2) - max(px1, gx1))
                    overlap_y = max(0, min(py2, gy2) - max(py1, gy1))
                    is_overlapping = (overlap_x > 0) and (overlap_y > 0)
                    
                    # Check 2: Center distance
                    distance = math.sqrt((pcx - gcx)**2 + (pcy - gcy)**2)
                    
                    if is_overlapping or distance < prox_thresh:
                        critical_alert_triggered = True

            # Determine alerts status
            if len(guns) > 0:
                if critical_alert_triggered:
                    alerts.append({
                        'type': 'CRITICAL',
                        'message': 'CRITICAL: Gun detected near a Person!',
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'details': f"Detected {len(persons)} Person(s), {len(bags)} Bag(s) and {len(guns)} Gun(s)."
                    })
                else:
                    high_alert_triggered = True
                    alerts.append({
                        'type': 'HIGH',
                        'message': 'HIGH ALERT: Gun detected in scene!',
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'details': f"Gun detected, but not close to any person. Total guns: {len(guns)}."
                    })
            elif len(persons) > 0:
                alerts.append({
                    'type': 'INFO',
                    'message': 'Active monitoring: Scene normal.',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'details': f"Detected {len(persons)} Person(s) and {len(bags)} Bag(s)."
                })

            # Save to Cache
            self.last_persons = persons
            self.last_bags = bags
            self.last_guns = guns
            self.last_critical = critical_alert_triggered
            self.last_high = high_alert_triggered
            self.last_alerts = alerts

        else:
            # Skip frame inference: load from cache
            persons = self.last_persons
            bags = self.last_bags
            guns = self.last_guns
            critical_alert_triggered = self.last_critical
            high_alert_triggered = self.last_high
            # Empty array on skipped frames to prevent log duplication in browser
            alerts = []

        # 4. Rendering Bounding Boxes on the Frame (Always done)
        # Draw proximity lines connecting Persons and Guns if critical
        if critical_alert_triggered:
            for p in persons:
                pcx, pcy = p['center']
                for g in guns:
                    gcx, gcy = g['center']
                    # Draw a line connecting the person and the gun
                    cv2.line(frame, (pcx, pcy), (gcx, gcy), (0, 0, 255), config.BOX_THICKNESS, cv2.LINE_AA)
                    distance = math.sqrt((pcx - gcx)**2 + (pcy - gcy)**2)
                    mid_x, mid_y = int((pcx + gcx) / 2), int((pcy + gcy) / 2)
                    cv2.putText(frame, f"{int(distance)}px", (mid_x, mid_y - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, config.FONT_SCALE, (0, 0, 255), config.FONT_THICKNESS, cv2.LINE_AA)

        # Helper to draw bounding box and label dynamically
        def draw_labeled_box(img, box, text, box_color, text_color):
            x1, y1, x2, y2 = box
            # Draw main bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), box_color, config.BOX_THICKNESS, cv2.LINE_AA)
            
            # Dynamic size calculation for label
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = config.FONT_SCALE
            font_thickness = config.FONT_THICKNESS
            
            (text_w, text_h), baseline = cv2.getTextSize(text, font_face, font_scale, font_thickness)
            
            padding = 12
            box_w = text_w + padding
            box_h = text_h + padding
            
            # Clip position to make sure it doesn't go off-screen
            # If label goes off the top edge, draw it inside the box
            if y1 - box_h < 0:
                cv2.rectangle(img, (x1, y1), (x1 + box_w, y1 + box_h), box_color, -1)
                cv2.putText(img, text, (x1 + padding // 2, y1 + text_h + padding // 2), 
                            font_face, font_scale, text_color, font_thickness, cv2.LINE_AA)
            else:
                cv2.rectangle(img, (x1, y1 - box_h), (x1 + box_w, y1), box_color, -1)
                cv2.putText(img, text, (x1 + padding // 2, y1 - padding // 2), 
                            font_face, font_scale, text_color, font_thickness, cv2.LINE_AA)

        # Draw Bags (Green)
        for b in bags:
            x1, y1, x2, y2 = b['box']
            label = b['label']
            conf = b['conf']
            draw_labeled_box(frame, (x1, y1, x2, y2), f"{label} {conf:.2f}", (0, 200, 0), (255, 255, 255))

        # Draw Persons (Blue/Cyan)
        for p in persons:
            x1, y1, x2, y2 = p['box']
            conf = p['conf']
            draw_labeled_box(frame, (x1, y1, x2, y2), f"Person {conf:.2f}", (255, 200, 0), (0, 0, 0))

        # Draw Guns (Red)
        for g in guns:
            x1, y1, x2, y2 = g['box']
            conf = g['conf']
            draw_labeled_box(frame, (x1, y1, x2, y2), f"GUN {conf:.2f}", (0, 0, 255), (255, 255, 255))

        # Helper to draw top banner overlay dynamically centered
        def draw_banner(img, text, bg_color, fg_color, banner_height=80):
            cv2.rectangle(img, (0, 0), (w, banner_height), bg_color, -1)
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = config.FONT_SCALE
            font_thickness = config.FONT_THICKNESS
            (text_w, text_h), _ = cv2.getTextSize(text, font_face, font_scale, font_thickness)
            text_x = max(10, int((w - text_w) / 2))
            text_y = int((banner_height + text_h) / 2)
            cv2.putText(img, text, (text_x, text_y), font_face, font_scale, fg_color, font_thickness, cv2.LINE_AA)

        # Draw visual banner overlays for threat status
        if critical_alert_triggered:
            # Pulsing Red Banner at top
            pulse = int((time.time() * 5) % 2)
            banner_color = (0, 0, 200) if pulse == 0 else (0, 0, 255)
            draw_banner(frame, "!!! CRITICAL THREAT: PERSON WITH GUN !!!", banner_color, (255, 255, 255), 80)
            cv2.rectangle(frame, (0, 0), (w, h), banner_color, config.BOX_THICKNESS * 2)
            
        elif high_alert_triggered:
            # Static Orange Banner at top
            draw_banner(frame, "WARNING: WEAPON DETECTED IN SCENE", (0, 140, 255), (0, 0, 0), 80)
            cv2.rectangle(frame, (0, 0), (w, h), (0, 140, 255), config.BOX_THICKNESS * 2)

        # 5. Handle Alert Snapshots (Only on inference frames to avoid duplicate copies)
        if run_inference and len(guns) > 0 and len(alerts) > 0:
            current_time = time.time()
            if current_time - self.last_snapshot_time > self.snapshot_cooldown:
                self.last_snapshot_time = current_time
                self._save_snapshot(frame, alerts[0])

        return frame, alerts

    def _save_snapshot(self, frame, alert_info):
        """Saves a frame snapshot to the static/alerts folder for historical viewing."""
        try:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            alert_type = alert_info['type'].lower()
            filename = f"snapshot_{alert_type}_{timestamp_str}.jpg"
            filepath = os.path.join(config.ALERTS_DIR, filename)
            
            # Save image
            cv2.imwrite(filepath, frame)
            
            # Attach filename back to alert_info for database/history display
            alert_info['snapshot'] = f"/static/alerts/{filename}"
            logger.info(f"Saved alert snapshot to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
