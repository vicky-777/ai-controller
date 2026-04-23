==========================================================
  AI Fan Controller — Complete Setup Guide
==========================================================

PROJECT OVERVIEW
----------------
User types anything → Groq AI decides speed → MQTT →
ESP8266 → L298N motor driver → DC fan


FOLDER STRUCTURE
----------------
  fan_controller.py        ← Python backend (run on PC/laptop)
  esp8266_fan_control.ino  ← Arduino sketch (flash to ESP8266)


==========================================================
PART 1 — HARDWARE WIRING
==========================================================

Components needed:
  - ESP8266 (NodeMCU or Wemos D1 Mini)
  - L298N motor driver module
  - DC toy fan (3V–12V)
  - External power supply (match your fan voltage)
  - Jumper wires

Wiring:
  ESP8266 D1 (GPIO5)  →  L298N ENA       (PWM signal)
  ESP8266 D2 (GPIO4)  →  L298N IN1       (set HIGH for direction)
  ESP8266 D3 (GPIO0)  →  L298N IN2       (set LOW for direction)
  ESP8266 GND         →  L298N GND
  External power +    →  L298N VCC (+12V or match fan)
  External power GND  →  L298N GND
  L298N OUT1          →  Fan motor wire 1
  L298N OUT2          →  Fan motor wire 2

  NOTE: Remove the ENA jumper on L298N if present —
        that jumper keeps it always at full speed.
        Removing it lets PWM control the speed.

Optional DHT22 sensor:
  DHT22 VCC   →  ESP8266 3.3V
  DHT22 GND   →  ESP8266 GND
  DHT22 DATA  →  ESP8266 D4 (GPIO2)
  (Also uncomment DHT lines in the .ino file)


==========================================================
PART 2 — THINGSPEAK SETUP
==========================================================

1. Go to https://thingspeak.com → Sign up (free)
2. Click "New Channel"
3. Name it: Fan Controller
4. Field 1 label: Fan Speed Level
   (0=off, 1=low, 2=medium, 3=high)
5. Field 2 label: Temperature (optional, if using DHT22)
6. Field 3 label: Humidity    (optional, if using DHT22)
7. Save Channel
8. Go to API Keys tab → copy the Write API Key
9. Paste it in esp8266_fan_control.ino:
     const char* TS_API_KEY = "PASTE_HERE";
10. Copy your Channel ID (shown in channel page URL)
    Paste it in fan_controller.py HTML section:
      href="https://thingspeak.com/channels/YOUR_CHANNEL_ID"


==========================================================
PART 3 — GROQ API SETUP
==========================================================

1. Go to https://console.groq.com → Sign up (free)
2. Click "API Keys" → "Create API Key"
3. Copy the key
4. Paste it in fan_controller.py:
     GROQ_API_KEY = "PASTE_HERE"

Free tier limits: 14,400 requests/day — more than enough


==========================================================
PART 4 — ESP8266 ARDUINO SETUP
==========================================================

Step 1 — Install Arduino IDE
  Download from: https://www.arduino.cc/en/software

Step 2 — Add ESP8266 board support
  File → Preferences → Additional Boards Manager URLs:
  Paste: https://arduino.esp8266.com/stable/package_esp8266com_index.json
  Tools → Board → Boards Manager → search "esp8266" → Install

Step 3 — Install libraries (Tools → Manage Libraries):
  - PubSubClient   by Nick O'Leary
  - ArduinoJson    by Benoit Blanchon
  - DHT sensor     by Adafruit  (only if using DHT22)

Step 4 — Edit esp8266_fan_control.ino:
  Fill in your values:
    WIFI_SSID        = "your wifi name"
    WIFI_PASSWORD    = "your wifi password"
    TS_API_KEY       = "your thingspeak write api key"
  Change MQTT_CLIENT_ID to something unique if needed

Step 5 — Flash to ESP8266:
  Tools → Board → NodeMCU 1.0  (or Wemos D1 Mini)
  Tools → Port → select your COM port
  Click Upload (→)
  Open Serial Monitor at 115200 baud to see logs


==========================================================
PART 5 — PYTHON BACKEND SETUP
==========================================================

Step 1 — Install Python 3.9+
  Download from: https://www.python.org

Step 2 — Install dependencies:
  Open terminal / command prompt:
    pip install flask flask-socketio paho-mqtt groq

Step 3 — Edit fan_controller.py:
  Fill in:
    GROQ_API_KEY = "your groq api key"
  Update ThingSpeak channel link in HTML section

Step 4 — Run:
  python fan_controller.py

Step 5 — Open browser:
  http://localhost:5000


==========================================================
PART 6 — TESTING
==========================================================

1. Flash ESP8266 → open Serial Monitor → confirm WiFi connects
2. Run fan_controller.py → confirm MQTT connects
3. Open http://localhost:5000 in browser
4. Type "it's very hot" → AI should pick "high"
5. Fan should spin at full speed
6. Check ThingSpeak dashboard — graph should show value 3
7. Try quick buttons: Off / Low / Medium / High

Expected Serial Monitor output on ESP8266:
  === DC Fan Controller — ESP8266 ===
  Connecting to WiFi: YourWiFi....
  WiFi connected!
  IP address: 192.168.1.x
  Connecting to MQTT broker...connected!
  Subscribed to: home/fan/set
  === Setup complete. Waiting for commands... ===
  MQTT received on [home/fan/set]: {"speed":"high"}
  Fan set to: high  (PWM=1023)
  ThingSpeak updated OK


==========================================================
TROUBLESHOOTING
==========================================================

Fan not spinning?
  → Check ENA jumper is removed from L298N
  → Verify external power supply is connected to L298N VCC
  → Test fan directly with power supply first
  → Check IN1=HIGH, IN2=LOW in Serial Monitor

ESP8266 not connecting to WiFi?
  → Double check SSID and password (case sensitive)
  → Make sure it's a 2.4GHz network (ESP8266 doesn't support 5GHz)
  → Move ESP8266 closer to router for testing

MQTT not connecting?
  → Try alternate broker: test.mosquitto.org port 1883
  → Check firewall isn't blocking port 1883

Groq returning wrong speed?
  → Check API key is correct
  → Check internet connection on the PC running Python

ThingSpeak not updating?
  → ThingSpeak free tier requires 15 second minimum between updates
  → TS_INTERVAL is set to 15000ms (15s) — do not lower it
  → Verify API key is the WRITE key not the READ key


==========================================================
SPEED → PWM REFERENCE
==========================================================

  Level    PWM Value   Duty Cycle   Approx Fan Speed
  -------  ---------   ----------   ----------------
  off      0           0%           stopped
  low      307         30%          gentle
  medium   665         65%          moderate
  high     1023        100%         full


==========================================================
THINGSPEAK FIELD REFERENCE
==========================================================

  field1 = fan speed numeric (0/1/2/3)
  field2 = temperature in °C (if DHT22 connected)
  field3 = humidity in %     (if DHT22 connected)
==========================================================
