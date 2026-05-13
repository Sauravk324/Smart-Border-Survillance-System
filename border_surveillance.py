#!/usr/bin/env python3
"""
Smart Border Surveillance System
Raspberry Pi 5 with PIR, Sound Sensor, Camera, and YOLO Detection
Telegram Integration for Alerts
"""

import lgpio
import time
import cv2
import numpy as np
import threading
import os
import asyncio
import logging
from datetime import datetime
from picamera2 import Picamera2
from telegram import Bot
from telegram.error import TelegramError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
# GPIO Pins
PIR_PIN = 17      # PIR sensor output
SOUND_PIN = 27    # Sound sensor output
BUZZER_PIN = 22   # Buzzer control

# Telegram Configuration - UPDATED WITH YOUR CREDENTIALS
TELEGRAM_BOT_TOKEN = "8224522553:AAGY3caC3qz6hImTBfon600hPwdOylzRDvQ"
TELEGRAM_CHAT_ID = "5053578580"

# YOLO Configuration
MODELS_PATH = "/home/saurav/border_surveillance/models"
YOLO_CONFIG = f"{MODELS_PATH}/yolov4-tiny.cfg"
YOLO_WEIGHTS = f"{MODELS_PATH}/yolov4-tiny.weights"
YOLO_CLASSES = f"{MODELS_PATH}/coco.names"
CONFIDENCE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4

# System Configuration
CAPTURE_INTERVAL = 10  # Minimum seconds between captures
BUZZER_DURATION = 0.5  # Buzzer duration in seconds
COOLDOWN_TIME = 10     # Seconds to wait after trigger before allowing another

# ==================== GPIO SETUP ====================
try:
    # Open GPIO chip
    h = lgpio.gpiochip_open(0)
    
    # Configure pins
    lgpio.gpio_claim_input(h, PIR_PIN, lgpio.SET_PULL_DOWN)
    lgpio.gpio_claim_input(h, SOUND_PIN)
    lgpio.gpio_claim_output(h, BUZZER_PIN)
    
    logger.info("GPIO initialized successfully")
except Exception as e:
    logger.error(f"GPIO initialization failed: {e}")
    exit(1)

# ==================== TELEGRAM BOT SETUP ====================
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ==================== CAMERA SETUP ====================
try:
    picam2 = Picamera2()
    camera_config = picam2.create_preview_configuration(main={"size": (640, 480)})
    picam2.configure(camera_config)
    picam2.start()
    time.sleep(2)  # Allow camera to warm up
    logger.info("Camera initialized successfully")
except Exception as e:
    logger.error(f"Camera initialization failed: {e}")
    exit(1)

# ==================== YOLO MODEL LOADING ====================
def load_yolo():
    """Load YOLO model and class names"""
    try:
        # Check if files exist
        if not os.path.exists(YOLO_CONFIG):
            logger.error(f"YOLO config not found: {YOLO_CONFIG}")
            return None, None
        if not os.path.exists(YOLO_WEIGHTS):
            logger.error(f"YOLO weights not found: {YOLO_WEIGHTS}")
            return None, None
        if not os.path.exists(YOLO_CLASSES):
            logger.error(f"YOLO classes not found: {YOLO_CLASSES}")
            return None, None
        
        # Load class names
        with open(YOLO_CLASSES, 'r') as f:
            classes = [line.strip() for line in f.readlines()]
        
        # Load YOLO network
        net = cv2.dnn.readNet(YOLO_WEIGHTS, YOLO_CONFIG)
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        
        logger.info(f"YOLO model loaded successfully with {len(classes)} classes")
        return net, classes
    except Exception as e:
        logger.error(f"Error loading YOLO model: {e}")
        return None, None

# Load YOLO
yolo_net, yolo_classes = load_yolo()

# ==================== DETECTION FUNCTIONS ====================
def detect_objects(image):
    """
    Detect objects in image using YOLO
    Returns list of detected objects with their classes and confidence
    """
    if yolo_net is None or yolo_classes is None:
        return []
    
    height, width = image.shape[:2]
    
    # Create blob from image
    blob = cv2.dnn.blobFromImage(image, 1/255.0, (416, 416), swapRB=True, crop=False)
    
    # Set input and forward pass
    yolo_net.setInput(blob)
    layer_names = yolo_net.getLayerNames()
    output_layers = [layer_names[i - 1] for i in yolo_net.getUnconnectedOutLayers()]
    
    # Run inference
    outputs = yolo_net.forward(output_layers)
    
    # Process detections
    boxes = []
    confidences = []
    class_ids = []
    
    for output in outputs:
        for detection in output:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            
            if confidence > CONFIDENCE_THRESHOLD:
                # Object detected
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                
                # Rectangle coordinates
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)
    
    # Apply Non-Maximum Suppression
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)
    
    detected_objects = []
    if len(indexes) > 0:
        for i in indexes.flatten():
            label = yolo_classes[class_ids[i]]
            
            # Check if it's human or vehicle
            if label == 'person':
                obj_type = 'HUMAN'
                color = (0, 255, 0)  # Green
            elif label in ['car', 'truck', 'bus', 'motorcycle', 'bicycle']:
                obj_type = 'VEHICLE'
                color = (255, 0, 0)  # Blue
            else:
                continue  # Skip other objects
                
            confidence = confidences[i]
            detected_objects.append({
                'type': obj_type,
                'label': label,
                'confidence': confidence,
                'box': boxes[i],
                'color': color
            })
    
    return detected_objects

def draw_detections(image, detections):
    """Draw bounding boxes around detected objects"""
    for detection in detections:
        x, y, w, h = detection['box']
        color = detection['color']
        
        # Draw bounding box
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
        
        # Draw label
        label = f"{detection['type']}: {detection['confidence']:.2f}"
        cv2.putText(image, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return image

# ==================== TELEGRAM FUNCTIONS ====================
async def send_telegram_alert(image_path, detection_info, trigger_type):
    """
    Send alert with image and detection info via Telegram
    """
    try:
        with open(image_path, 'rb') as photo:
            # Create caption
            if detection_info:
                caption = f"🚨 *BORDER ALERT* 🚨\n"
                caption += f"Trigger: {trigger_type}\n"
                caption += f"Detection: {detection_info['type']}\n"
                caption += f"Object: {detection_info['label']}\n"
                caption += f"Confidence: {detection_info['confidence']:.2f}\n"
            else:
                caption = f"⚠️ *BORDER ALERT* ⚠️\n"
                caption += f"Trigger: {trigger_type}\n"
                caption += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                caption += "No human/vehicle detected"
            
            caption += f"\nSystem: Smart Border Surveillance"
            
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=photo, caption=caption, parse_mode='Markdown')
            logger.info(f"Alert sent to Telegram: {trigger_type}")
            
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

def send_telegram_alert_sync(image_path, detection_info, trigger_type):
    """Synchronous wrapper for send_telegram_alert"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_telegram_alert(image_path, detection_info, trigger_type))
        loop.close()
    except Exception as e:
        logger.error(f"Telegram sync error: {e}")

# ==================== CAPTURE AND PROCESS ====================
def capture_and_process(trigger_type):
    """
    Capture image, detect objects, and send alert
    """
    try:
        # Capture image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create captures directory if it doesn't exist
        captures_dir = "/home/saurav/border_surveillance/captures"
        os.makedirs(captures_dir, exist_ok=True)
        
        image_path = f"{captures_dir}/{trigger_type}_{timestamp}.jpg"
        
        # Capture frame
        frame = picam2.capture_array()
        
        # Convert RGB to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Add timestamp to image
        cv2.putText(frame_bgr, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame_bgr, f"Trigger: {trigger_type}", (10, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Detect objects
        detections = detect_objects(frame_bgr)
        
        # Draw detections on image
        if detections:
            frame_bgr = draw_detections(frame_bgr, detections)
            logger.info(f"Detected: {len(detections)} object(s)")
            for d in detections:
                logger.info(f"  - {d['type']}: {d['label']} ({d['confidence']:.2f})")
        
        # Save image
        cv2.imwrite(image_path, frame_bgr)
        logger.info(f"Image saved: {image_path}")
        
        # Trigger buzzer
        lgpio.gpio_write(h, BUZZER_PIN, 1)
        time.sleep(BUZZER_DURATION)
        lgpio.gpio_write(h, BUZZER_PIN, 0)
        
        # Send Telegram alert
        if detections:
            detection_info = detections[0]  # Send most confident detection
        else:
            detection_info = None
        
        # Send alert in background thread
        alert_thread = threading.Thread(
            target=send_telegram_alert_sync, 
            args=(image_path, detection_info, trigger_type)
        )
        alert_thread.start()
        
        return True
        
    except Exception as e:
        logger.error(f"Error in capture and process: {e}")
        return False

# ==================== SENSOR MONITORING ====================
class SensorMonitor:
    def __init__(self):
        self.last_trigger_time = 0
        self.pir_last_state = 0
        self.sound_last_state = 0
        self.lock = threading.Lock()
        
    def can_trigger(self):
        """Check if enough time has passed since last trigger"""
        with self.lock:
            current_time = time.time()
            if current_time - self.last_trigger_time >= COOLDOWN_TIME:
                self.last_trigger_time = current_time
                return True
        return False
    
    def monitor_pir(self):
        """Monitor PIR sensor in a thread"""
        logger.info("PIR monitoring started")
        while True:
            try:
                pir_state = lgpio.gpio_read(h, PIR_PIN)
                
                # Detect rising edge (0 to 1)
                if pir_state == 1 and self.pir_last_state == 0:
                    if self.can_trigger():
                        logger.info("🔴 PIR MOTION DETECTED!")
                        # Run capture in separate thread to not block monitoring
                        capture_thread = threading.Thread(target=capture_and_process, args=("PIR",))
                        capture_thread.start()
                    else:
                        logger.debug("PIR ignored (cooldown)")
                
                self.pir_last_state = pir_state
                time.sleep(0.05)  # Small delay to prevent CPU overload
                
            except Exception as e:
                logger.error(f"PIR monitoring error: {e}")
                time.sleep(1)
    
    def monitor_sound(self):
        """Monitor sound sensor in a thread"""
        logger.info("Sound monitoring started")
        while True:
            try:
                sound_state = lgpio.gpio_read(h, SOUND_PIN)
                
                # Detect rising edge (0 to 1)
                if sound_state == 1 and self.sound_last_state == 0:
                    if self.can_trigger():
                        logger.info("🔊 SOUND DETECTED!")
                        # Run capture in separate thread
                        capture_thread = threading.Thread(target=capture_and_process, args=("SOUND",))
                        capture_thread.start()
                    else:
                        logger.debug("Sound ignored (cooldown)")
                
                self.sound_last_state = sound_state
                time.sleep(0.05)
                
            except Exception as e:
                logger.error(f"Sound monitoring error: {e}")
                time.sleep(1)

# ==================== MAIN FUNCTION ====================
def main():
    try:
        logger.info("=" * 60)
        logger.info("SMART BORDER SURVEILLANCE SYSTEM STARTING")
        logger.info("=" * 60)
        logger.info(f"Telegram Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...")
        logger.info(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
        logger.info("=" * 60)
        
        # Send startup notification
        try:
            # Create a simple startup message without image
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bot.send_message(
                chat_id=TELEGRAM_CHAT_ID, 
                text="🚀 *Border Surveillance System Started*\n\nMonitoring PIR and Sound sensors...", 
                parse_mode='Markdown'
            ))
            loop.close()
            logger.info("Startup notification sent to Telegram")
        except Exception as e:
            logger.warning(f"Could not send startup notification: {e}")
        
        # Create monitor instance
        monitor = SensorMonitor()
        
        # Start monitoring threads
        pir_thread = threading.Thread(target=monitor.monitor_pir, daemon=True)
        sound_thread = threading.Thread(target=monitor.monitor_sound, daemon=True)
        
        pir_thread.start()
        sound_thread.start()
        
        logger.info("System is running. Press Ctrl+C to stop.")
        logger.info(f"Cooldown: {COOLDOWN_TIME}s between captures")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("System stopped by user")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Cleanup
        try:
            picam2.stop()
            lgpio.gpiochip_close(h)
            logger.info("Cleanup complete")
        except:
            pass

# ==================== START SYSTEM ====================
if __name__ == "__main__":
    main()
