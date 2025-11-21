from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta # Pastikan timedelta di-import
import json
import random
from flask_mqtt import Mqtt

app = Flask(__name__)

# Konfigurasi MQTT
app.config['MQTT_BROKER_URL'] = 'localhost'  # Tetap localhost karena satu server
app.config['MQTT_BROKER_PORT'] = 1883
app.config['MQTT_USERNAME'] = 'username_kamu'  # Yang dibuat di Langkah 2
app.config['MQTT_PASSWORD'] = 'password_kamu'
app.config['MQTT_REFRESH_TIME'] = 1.0  # refresh time in seconds

mqtt = Mqtt(app)

# --- Konfigurasi Aplikasi ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///irrigation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- [BARU] Konfigurasi Waktu Offline ---
# Anggap ESP offline jika tidak ada data baru selama 300 detik (5 menit)
ESP_OFFLINE_THRESHOLD = 300 

# --- Status Pompa ---
PUMP_STATE = {"state": "OFF"}

# --- Model Database ---
# (Tidak ada perubahan di sini)
class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    soil_moisture = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    rainfall = db.Column(db.Float, nullable=True) 
    pump_state = db.Column(db.String(10), nullable=False, default="OFF")

    def __repr__(self):
        return f'<Data {self.timestamp}>'
    
    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "soil_moisture": self.soil_moisture,
            "humidity": self.humidity,
            "temperature": self.temperature,
            "rainfall": self.rainfall,
            "pump_state": self.pump_state
        }

# --- Rute Halaman ---

@app.route('/')
def home():
    """Menampilkan halaman dashboard 'Home' (data terkini)."""
    return render_template('home.html')

@app.route('/history')
def history():
    """Menampilkan halaman 'History' (grafik)."""
    return render_template('history.html')


@app.route('/status')
def status():
    """[BARU] Menampilkan halaman status perangkat dan tabel data."""
    
    # --- Logika Cek Status ESP ---
    esp_status = "Unknown"
    last_seen_time = None
    
    # 1. Ambil data paling baru dari database
    latest_data = SensorData.query.order_by(SensorData.timestamp.desc()).first()
    
    if latest_data:
        # 2. Hitung selisih waktu antara sekarang dan data terakhir
        last_seen_time = latest_data.timestamp
        time_diff = (datetime.utcnow() - last_seen_time).total_seconds()
        
        # 3. Tentukan status
        if time_diff > ESP_OFFLINE_THRESHOLD:
            esp_status = "Offline"
        else:
            esp_status = "Online"
    
    # --- Logika Tabel Data & Pagination ---
    # Ambil nomor halaman dari URL (default ke halaman 1)
    page = request.args.get('page', 1, type=int)
    
    # Query data dari database, urutkan dari yang terbaru, dan paginasi
    # Menampilkan 15 entri per halaman
    pagination = SensorData.query.order_by(SensorData.timestamp.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    
    # Kirim semua data ke template
    return render_template(
        'status.html', 
        esp_status=esp_status, 
        last_seen_time=last_seen_time, 
        pagination=pagination
    )


# --- Rute API ---

@app.route('/api/latest-status')
def get_latest_status():
    """API untuk halaman 'Home'."""
    latest_data = SensorData.query.order_by(SensorData.timestamp.desc()).first()
    data_json = latest_data.to_dict() if latest_data else {"soil_moisture": 0, "humidity": 0, "temperature": 0, "rainfall": 0, "timestamp": "N/A"}
    return jsonify({
        "sensor_data": data_json,
        "pump_status": PUMP_STATE
    })

@app.route('/api/chart-data')
def get_chart_data():
    """API untuk halaman 'History' (grafik)."""
    data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(50).all()
    data.reverse() 
    chart_data = {
        "labels": [d.timestamp.strftime('%H:%M:%S') for d in data],
        "soil_moisture": [d.soil_moisture for d in data],
        "humidity": [d.humidity for d in data],
        "temperature": [d.temperature for d in data],
        "rainfall": [d.rainfall for d in data]
    }
    return jsonify(chart_data)

import json

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    payload_str = message.payload.decode()
    try:
        data = json.loads(payload_str) # Parsing JSON
        
        suhu = data.get('suhu_udara')
        tanah = data.get('kelembapan_tanah')
        
        print(f"Suhu: {suhu}, Tanah: {tanah}%")
        new_data = SensorData(
                soil_moisture=data['soil_moisture'],
                humidity=data['humidity'],
                temperature=data['temperature'],
                rainfall=data['rainfall']
            )
        db.session.add(new_data)
        db.session.commit()
        return jsonify({"message": "Data berhasil diterima!"}), 201
        
    except Exception as e:
        print("Error parsing JSON:", e)

@app.route('/data', methods=['POST'])
def receive_data():
    """API untuk ESP32."""
    if request.is_json:
        data = request.get_json()
        try:
            new_data = SensorData(
                soil_moisture=data['soil_moisture'],
                humidity=data['humidity'],
                temperature=data['temperature'],
                rainfall=data['rainfall']
            )
            db.session.add(new_data)
            db.session.commit()
            return jsonify({"message": "Data berhasil diterima!"}), 201
        except KeyError:
            return jsonify({"error": "Data tidak lengkap."}), 400
        except Exception as e:
            db.session.rollback(); return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Request harus dalam format JSON"}), 400

@app.route('/irrigate', methods=['POST'])
def manual_irrigate():
    """Endpoint untuk tombol irigasi (toggle)."""
    global PUMP_STATE
    if PUMP_STATE["state"] == "OFF":
        PUMP_STATE["state"] = "ON"
        message = "Pompa berhasil diaktifkan!"
        print("PERINTAH MANUAL: Mengirim sinyal ON ke ESP32...")
    else:
        PUMP_STATE["state"] = "OFF"
        message = "Pompa berhasil dimatikan!"
        print("PERINTAH MANUAL: Mengirim sinyal OFF ke ESP32...")
    
    return jsonify({"message": message, "state": PUMP_STATE["state"]}), 200

# --- Menjalankan Aplikasi ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # --- [BLOK DATA DUMMY] ---
        if SensorData.query.count() == 0:
            print("Database kosong. Mengisi dengan data dummy...")
            now = datetime.utcnow()
            for i in range(50): # Buat 50 data agar bisa tes paginasi
                dummy_data = SensorData(
                    soil_moisture=round(random.uniform(30.0, 80.0), 2),
                    humidity=round(random.uniform(40.0, 70.0), 2),
                    temperature=round(random.uniform(25.0, 32.0), 2),
                    rainfall=round(random.choice([0, 0, 0, 0, 0, 1.2, 3.0, 0.5]), 2), 
                    timestamp=now - timedelta(minutes=i*5) 
                )
                db.session.add(dummy_data)
            db.session.commit()
            print("Data dummy berhasil ditambahkan.")
        # --- [AKHIR BLOK DUMMY] ---
            
    app.run(debug=True, host='0.0.0.0', port=5000)