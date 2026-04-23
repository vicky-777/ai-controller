

import json
import threading
import time
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
from groq import Groq

# ── Configuration ─────────────────────────────────────────
GROQ_API_KEY  = "*****"   # from console.groq.com (free)
MQTT_BROKER   = "broker.hivemq.com"   # free public broker
MQTT_PORT     = 1883
MQTT_TOPIC    = "home/fan/set"        # publish commands here
MQTT_STATUS   = "home/fan/status"     # listen for ESP8266 status here

# ── Groq AI system prompt ─────────────────────────────────
# This tells the AI exactly what to do — keep it strict
SYSTEM_PROMPT = """
You are a fan speed controller AI.
The user will describe how they feel or what they want.
You must respond with ONLY one of these four words — nothing else:
  off
  low
  medium
  high

Rules:
- "off", "stop", "turn off", "I'm cold", "too cold" → off
- "a little", "slight breeze", "low", "gentle" → low
- "medium", "normal", "moderate", "okay speed" → medium
- "hot", "very hot", "max", "high", "full speed", "boiling" → high
- If unsure, pick medium
- NEVER explain yourself. Output only one word.
"""

# ── Flask + SocketIO app ──────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'fansecret123'
socketio = SocketIO(app, cors_allowed_origins="*")

# ── State ─────────────────────────────────────────────────
current_speed  = "off"
groq_client    = Groq(api_key=GROQ_API_KEY)
mqtt_client    = mqtt.Client()

# ── HTML template (web UI) ────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Fan Controller</title>
  <script src="https://cdn.socket.io/4.6.1/socket.io.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: system-ui, sans-serif;
      background: #0f0f0f;
      color: #f0f0f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .card {
      background: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 16px;
      padding: 40px;
      width: 100%;
      max-width: 500px;
    }

    h1 {
      font-size: 22px;
      font-weight: 600;
      margin-bottom: 6px;
      color: #ffffff;
    }

    .subtitle {
      font-size: 13px;
      color: #666;
      margin-bottom: 32px;
    }

    /* Fan speed display */
    .speed-display {
      display: flex;
      gap: 10px;
      margin-bottom: 28px;
    }

    .speed-pill {
      flex: 1;
      padding: 10px 0;
      border-radius: 8px;
      text-align: center;
      font-size: 13px;
      font-weight: 500;
      background: #252525;
      color: #555;
      border: 1px solid #2a2a2a;
      transition: all 0.3s;
    }

    .speed-pill.active-off    { background:#2a2a2a; color:#fff; border-color:#444; }
    .speed-pill.active-low    { background:#0d3b2e; color:#4ade80; border-color:#166534; }
    .speed-pill.active-medium { background:#2d2000; color:#fbbf24; border-color:#854d0e; }
    .speed-pill.active-high   { background:#3b0a0a; color:#f87171; border-color:#991b1b; }

    /* Fan icon */
    .fan-icon {
      font-size: 64px;
      text-align: center;
      margin-bottom: 20px;
      transition: transform 0.3s;
      user-select: none;
    }

    .fan-icon.spin-slow   { animation: spin 2s linear infinite; }
    .fan-icon.spin-medium { animation: spin 0.8s linear infinite; }
    .fan-icon.spin-fast   { animation: spin 0.3s linear infinite; }

    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

    /* Input area */
    label {
      display: block;
      font-size: 13px;
      color: #888;
      margin-bottom: 8px;
    }

    .input-row {
      display: flex;
      gap: 10px;
      margin-bottom: 16px;
    }

    input[type="text"] {
      flex: 1;
      background: #252525;
      border: 1px solid #333;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 15px;
      color: #f0f0f0;
      outline: none;
      transition: border-color 0.2s;
    }

    input[type="text"]:focus { border-color: #555; }

    button {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 8px;
      padding: 12px 20px;
      font-size: 15px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
      white-space: nowrap;
    }

    button:hover    { background: #1d4ed8; }
    button:disabled { background: #333; color: #666; cursor: not-allowed; }

    /* Quick buttons */
    .quick-btns {
      display: flex;
      gap: 8px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }

    .quick-btn {
      flex: 1;
      min-width: 80px;
      background: #252525;
      color: #aaa;
      border: 1px solid #333;
      border-radius: 8px;
      padding: 8px 0;
      font-size: 13px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .quick-btn:hover { background: #333; color: #fff; border-color: #555; }

    /* Log */
    .log-label {
      font-size: 12px;
      color: #555;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
    }

    .log {
      background: #111;
      border: 1px solid #222;
      border-radius: 8px;
      padding: 12px;
      font-size: 13px;
      font-family: monospace;
      height: 140px;
      overflow-y: auto;
      color: #666;
    }

    .log-entry { padding: 2px 0; border-bottom: 1px solid #1a1a1a; }
    .log-entry:last-child { border-bottom: none; }
    .log-entry .time { color: #444; margin-right: 8px; }
    .log-entry .msg  { color: #888; }
    .log-entry .speed-tag { 
      font-weight: bold; 
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 11px;
    }
    .tag-off    { background:#2a2a2a; color:#aaa; }
    .tag-low    { background:#0d3b2e; color:#4ade80; }
    .tag-medium { background:#2d2000; color:#fbbf24; }
    .tag-high   { background:#3b0a0a; color:#f87171; }

    .thingspeak-link {
      display: block;
      text-align: center;
      margin-top: 20px;
      font-size: 12px;
      color: #444;
      text-decoration: none;
    }
    .thingspeak-link:hover { color: #888; }

    .status-dot {
      display: inline-block;
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #666;
      margin-right: 6px;
      transition: background 0.3s;
    }
    .status-dot.connected { background: #4ade80; }
  </style>
</head>
<body>
<div class="card">

  <h1>🌬️ AI Fan Controller</h1>
  <p class="subtitle">
    <span class="status-dot" id="dot"></span>
    <span id="conn-status">Connecting...</span>
  </p>

  <!-- Fan animation -->
  <div class="fan-icon" id="fan-icon">💨</div>

  <!-- Speed level pills -->
  <div class="speed-display">
    <div class="speed-pill" id="pill-off">Off</div>
    <div class="speed-pill" id="pill-low">Low</div>
    <div class="speed-pill" id="pill-medium">Medium</div>
    <div class="speed-pill" id="pill-high">High</div>
  </div>

  <!-- Text input -->
  <label>Tell the AI what you need:</label>
  <div class="input-row">
    <input type="text" id="user-input" placeholder="e.g. it's too hot, slight breeze, turn off..." maxlength="200"/>
    <button id="send-btn" onclick="sendCommand()">Send</button>
  </div>

  <!-- Quick buttons -->
  <div class="quick-btns">
    <button class="quick-btn" onclick="quickSend('turn off the fan')">Off</button>
    <button class="quick-btn" onclick="quickSend('give me a gentle breeze')">Low</button>
    <button class="quick-btn" onclick="quickSend('medium speed please')">Medium</button>
    <button class="quick-btn" onclick="quickSend('it is very hot max speed')">High</button>
  </div>

  <!-- Log -->
  <div class="log-label">
    <span>Activity log</span>
    <span id="esp-status" style="color:#555">ESP8266: unknown</span>
  </div>
  <div class="log" id="log"></div>

  <a class="thingspeak-link" href="https://thingspeak.com/channels/3322642" target="_blank">
    📊 View ThingSpeak Dashboard →
  </a>

</div>

<script>
  const socket = io();
  let currentSpeed = 'off';

  socket.on('connect', () => {
    document.getElementById('dot').classList.add('connected');
    document.getElementById('conn-status').textContent = 'Connected';
  });

  socket.on('disconnect', () => {
    document.getElementById('dot').classList.remove('connected');
    document.getElementById('conn-status').textContent = 'Disconnected';
  });

  socket.on('speed_update', (data) => {
    updateUI(data.speed, data.user_input, data.ai_reasoning);
  });

  socket.on('esp_status', (data) => {
    document.getElementById('esp-status').textContent = 'ESP8266: ' + data.speed;
  });

  socket.on('error_msg', (data) => {
    addLog('⚠️ ' + data.message, null);
    document.getElementById('send-btn').disabled = false;
    document.getElementById('send-btn').textContent = 'Send';
  });

  function updateUI(speed, userInput, reasoning) {
    currentSpeed = speed;

    // Update pills
    ['off','low','medium','high'].forEach(s => {
      const p = document.getElementById('pill-' + s);
      p.className = 'speed-pill' + (s === speed ? ' active-' + speed : '');
    });

    // Update fan icon animation
    const icon = document.getElementById('fan-icon');
    icon.className = 'fan-icon';
    if (speed === 'low')    icon.classList.add('spin-slow');
    if (speed === 'medium') icon.classList.add('spin-medium');
    if (speed === 'high')   icon.classList.add('spin-fast');

    // Add log entry
    if (userInput) addLog(userInput, speed);

    document.getElementById('send-btn').disabled = false;
    document.getElementById('send-btn').textContent = 'Send';
  }

  function addLog(text, speed) {
    const log  = document.getElementById('log');
    const now  = new Date().toLocaleTimeString();
    const tag  = speed ? `<span class="speed-tag tag-${speed}">${speed}</span>` : '';
    const div  = document.createElement('div');
    div.className = 'log-entry';
    div.innerHTML = `<span class="time">${now}</span><span class="msg">${text}</span> ${tag}`;
    log.prepend(div);
  }

  function sendCommand() {
    const input = document.getElementById('user-input').value.trim();
    if (!input) return;
    document.getElementById('send-btn').disabled = true;
    document.getElementById('send-btn').textContent = 'Thinking...';
    socket.emit('user_command', { text: input });
    document.getElementById('user-input').value = '';
  }

  function quickSend(text) {
    document.getElementById('user-input').value = text;
    sendCommand();
  }

  document.getElementById('user-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendCommand();
  });
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────
# Groq AI — decide fan speed from user input
# ─────────────────────────────────────────────────────────
def ask_groq(user_input: str) -> str:
    """
    Send user input to Groq AI.
    Returns one of: 'off', 'low', 'medium', 'high'
    """
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # fast, free model on Groq
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_input}
            ],
            max_tokens=5,       # we only need one word back
            temperature=0.1,    # low temperature = more consistent output
        )

        speed = response.choices[0].message.content.strip().lower()

        # Sanitize — only accept valid values
        if speed not in ["off", "low", "medium", "high"]:
            print(f"[Groq] Unexpected response: '{speed}' — defaulting to medium")
            speed = "medium"

        print(f"[Groq] User: '{user_input}' → Speed: '{speed}'")
        return speed

    except Exception as e:
        print(f"[Groq] Error: {e}")
        return "off"  # fail safe

# ─────────────────────────────────────────────────────────
# MQTT — publish command to ESP8266
# ─────────────────────────────────────────────────────────
def publish_speed(speed: str):
    """Publish fan speed command as JSON to MQTT broker."""
    payload = json.dumps({"speed": speed})
    result  = mqtt_client.publish(MQTT_TOPIC, payload, qos=1, retain=True)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"[MQTT] Published: {payload}")
    else:
        print(f"[MQTT] Publish failed: rc={result.rc}")

# ─────────────────────────────────────────────────────────
# MQTT callbacks
# ─────────────────────────────────────────────────────────
def on_mqtt_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected to broker")
        client.subscribe(MQTT_STATUS)
        print(f"[MQTT] Subscribed to {MQTT_STATUS}")
    else:
        print(f"[MQTT] Connection failed: rc={rc}")

def on_mqtt_message(client, userdata, msg):
    """Handle status messages coming back from ESP8266."""
    try:
        payload = json.loads(msg.payload.decode())
        speed   = payload.get("speed", "unknown")
        print(f"[MQTT] ESP8266 status: {payload}")
        # Push ESP8266 status to web UI
        socketio.emit('esp_status', {'speed': speed})
    except Exception as e:
        print(f"[MQTT] Status parse error: {e}")

def on_mqtt_disconnect(client, userdata, rc):
    print(f"[MQTT] Disconnected: rc={rc} — reconnecting...")

# ─────────────────────────────────────────────────────────
# SocketIO — handle web UI events
# ─────────────────────────────────────────────────────────
@socketio.on('user_command')
def handle_command(data):
    user_input = data.get('text', '').strip()
    if not user_input:
        emit('error_msg', {'message': 'Empty input'})
        return

    print(f"\n[UI] User said: '{user_input}'")

    # Run Groq in a thread so Flask doesn't block
    def process():
        speed = ask_groq(user_input)
        publish_speed(speed)
        socketio.emit('speed_update', {
            'speed':      speed,
            'user_input': user_input,
        })

    thread = threading.Thread(target=process, daemon=True)
    thread.start()

# ─────────────────────────────────────────────────────────
# Flask route
# ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML)

# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
def start_mqtt():
    mqtt_client.on_connect    = on_mqtt_connect
    mqtt_client.on_message    = on_mqtt_message
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqtt_client.loop_forever()

if __name__ == '__main__':
    print("=" * 50)
    print("  AI Fan Controller — Backend")
    print("=" * 50)
    print(f"  MQTT broker : {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Web UI      : http://localhost:5000")
    print("=" * 50)

    # Start MQTT in background thread
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    # Give MQTT a moment to connect
    time.sleep(1)

    # Start Flask web server
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
