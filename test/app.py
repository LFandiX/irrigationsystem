import threading
from flask import Flask, render_template
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt

# --- Konfigurasi ---
BROKER_ADDRESS = "localhost"  # Ganti dengan broker Anda, misal "localhost"
MQTT_TOPIC = "sensors/drone01/altitude"
# --------------------

# Variabel global untuk menyimpan data terakhir (opsional, tapi berguna)
latest_altitude = "0.0"

# Setup Flask & SocketIO
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci_rahasia_anda!' # Ganti dengan kunci rahasia
socketio = SocketIO(app)

# --- Logika MQTT ---

def on_connect(client, userdata, flags, rc):
    """Callback saat berhasil terhubung ke broker."""
    if rc == 0:
        print(f"Berhasil terhubung ke broker di {BROKER_ADDRESS}")
        # Langsung subscribe ke topik setelah terhubung
        client.subscribe(MQTT_TOPIC)
        print(f"Berlangganan ke topik: {MQTT_TOPIC}")
    else:
        print(f"Gagal terhubung, kode balasan: {rc}")

def on_message(client, userdata, msg):
    """Callback saat menerima pesan dari topik yang di-subscribe."""
    global latest_altitude
    
    try:
        # 1. Ambil data dari pesan
        payload = msg.payload.decode('utf-8')
        print(f"Menerima pesan: {payload} dari topik {msg.topic}")
        latest_altitude = payload

        # 2. Siarkan (emit) data ke semua klien web via SocketIO
        #    'update_data' adalah nama event kustom
        socketio.emit('update_data', {'topic': msg.topic, 'payload': payload})
        
    except Exception as e:
        print(f"Error saat memproses pesan: {e}")

def setup_mqtt_client():
    """Setup dan jalankan klien MQTT di background."""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER_ADDRESS, 1883, 60)
        # loop_forever() adalah blocking call, ia akan berjalan di thread-nya sendiri
        client.loop_forever()
    except Exception as e:
        print(f"Tidak bisa terhubung ke broker MQTT: {e}")

# --- Rute Flask ---

@app.route('/')
def index():
    """Menyajikan halaman web utama (index.html)."""
    # Kita bisa kirim data terakhir saat halaman pertama kali di-load
    return render_template('index.html', initial_data=latest_altitude)

# --- Main ---

if __name__ == '__main__':
    # 1. Jalankan klien MQTT di thread terpisah
    print("Memulai background thread MQTT...")
    mqtt_thread = threading.Thread(target=setup_mqtt_client, daemon=True)
    mqtt_thread.start()
    
    # 2. Jalankan server Flask (SocketIO)
    print("Memulai server Flask-SocketIO di http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)