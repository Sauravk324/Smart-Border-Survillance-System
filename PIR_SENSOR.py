#!/usr/bin/env python3
"""
PIR Calibration using lgpio (works with Raspberry Pi 5)
"""

import lgpio
import time
from datetime import datetime

PIR_PIN = 17

# Open GPIO chip
h = lgpio.gpiochip_open(0)

# Configure PIR pin as input with pull-down
lgpio.gpio_claim_input(h, PIR_PIN, lgpio.SET_PULL_DOWN)

print("=" * 60)
print("PIR CALIBRATION TOOL (lgpio version)")
print("=" * 60)
print("\n🔧 To reduce sensitivity:")
print("  • Find the orange screw on the PIR sensor")
print("  • Turn it COUNTER-CLOCKWISE slowly")
print("  • Wait 10 seconds between adjustments")
print("\nPress Ctrl+C to stop")
print("=" * 60)

input("\nPress Enter to start...")

last_time = time.time()
count = 0
last_state = 0

try:
    while True:
        # Read current state
        state = lgpio.gpio_read(h, PIR_PIN)
        
        # Detect rising edge (0 to 1)
        if state == 1 and last_state == 0:
            current_time = time.time()
            count += 1
            
            if count == 1:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] First detection!")
            else:
                gap = current_time - last_time
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Detection #{count}")
                print(f"   Time since last: {gap:.1f} seconds")
                
                if gap < 2:
                    print("   ⚠️  TOO FREQUENT - Turn screw COUNTER-CLOCKWISE")
                elif gap < 5:
                    print("   👍 Getting better - small adjustment may help")
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
