#!/usr/bin/env python3
"""
Sound Calibration using lgpio
"""

import lgpio
import time
from datetime import datetime

SOUND_PIN = 27

# Open GPIO chip
h = lgpio.gpiochip_open(0)

# Configure sound pin as input
lgpio.gpio_claim_input(h, SOUND_PIN)

print("=" * 60)
print("SOUND CALIBRATION TOOL (lgpio version)")
print("=" * 60)
print("\n🔧 To reduce sensitivity:")
print("  • Find the blue screw on the sound sensor")
print("  • Turn it COUNTER-CLOCKWISE slowly")
print("  • Test with claps and normal conversation")
print("\nPress Ctrl+C to stop")
print("=" * 60)

input("\nPress Enter to start...")

last_time = time.time()
count = 0
last_state = 0

try:
    while True:
        # Read current state
        state = lgpio.gpio_read(h, SOUND_PIN)
        
        # Detect rising edge (0 to 1)
        if state == 1 and last_state == 0:
            current_time = time.time()
            count += 1
            
            if count == 1:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] First sound!")
            else:
                gap = current_time - last_time
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Sound #{count}")
                print(f"   Time since last: {gap:.1f} seconds")
                
                if gap < 1:
                    print("   ⚠️  TOO FREQUENT - Turn screw COUNTER-CLOCKWISE")
                elif gap < 3:
                    print("   👍 Getting better - keep adjusting")
                else:
                    print("   ✅ Good sensitivity!")
            
            last_time = current_time
            time.sleep(0.5)  # Debounce
        
        last_state = state
        time.sleep(0.05)
        
except KeyboardInterrupt:
    print("\n\nCalibration stopped")
    print(f"Total detections: {count}")
    
finally:
    lgpio.gpiochip_close(h)
    print("GPIO closed")
