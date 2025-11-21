from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import random
from flask_mqtt import Mqtt
import requests

# --- Konfigurasi Aplikasi ---
app = Flask(__name__)

# --- Konfigurasi MQTT ---
app.config['MQTT_BROKER_URL'] = 'localhost'  
app.config['MQTT_BROKER_PORT'] = 1883
# app.config['MQTT_USERNAME'] = 'username_kamu'  # Ganti sesuai setup VPS
# app.config['MQTT_PASSWORD'] = 'password_kamu'  # Ganti sesuai setup VPS
app.config['MQTT_REFRESH_TIME'] = 1.0 
app.config['MQTT_TLS_ENABLED'] = False

mqtt = Mqtt(app)

# --- Konfigurasi Database ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///irrigation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Konfigurasi Waktu Offline ---
ESP_OFFLINE_THRESHOLD = 300 

WEATHER_API_URL = "https://api.weatherapi.com/v1/current.json?key=ef75434afd084933a3a64248251411&q=-6.2,106.816666"

# --- Status Pompa Global ---
LAST_PUMP_STATUS = "OFF"

# --- Model Database ---
class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    soil_moisture = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    rainfall = db.Column(db.Float, nullable=True) 

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "soil_moisture": self.soil_moisture,
            "humidity": self.humidity,
            "temperature": self.temperature,
            "rainfall": self.rainfall
        }
    

def get_rainfall_from_api():
    """Mengambil data precip_mm dari WeatherAPI.com"""
    try:
        # Request ke URL API
        response = requests.get(WEATHER_API_URL, timeout=5)
        data = response.json()
        
        # Parsing JSON sesuai output yang Anda kirimkan:
        # data -> current -> precip_mm
        curah_hujan = data.get('current', {}).get('precip_mm', 0.0)
        
        return curah_hujan
        
    except Exception as e:
        print(f"Gagal ambil data cuaca: {e}")
        return 0.0 # Default nilai 0 jika error/internet putus
# ==========================================
# LOGIKA MQTT (BACKEND KOMUNIKASI)
# ==========================================

@mqtt.on_connect()
def handle_connect(client, userdata, flags, rc):
    """Berjalan otomatis saat Flask terhubung ke Broker MQTT"""
    if rc == 0:
        print("Terhubung ke MQTT Broker!")
        # Subscribe ke topik data sensor dari ESP32
        mqtt.subscribe('kebun/data')
    else:
        print("Gagal terhubung ke MQTT, kode:", rc)

@mqtt.on_message()
def handle_mqtt_message(client, userdata, message):
    """
    Setiap kali ESP32 kirim data sensor (suhu/tanah),
    Flask akan otomatis mengambil data hujan dari API,
    lalu menyimpannya bersamaan ke database.
    """
    global LAST_PUMP_STATUS
    try:
        payload_str = message.payload.decode()
        print(f"Pesan Masuk [{message.topic}]: {payload_str}")
        
        data = json.loads(payload_str)
        
        # 1. Ambil data sensor dari ESP32
        suhu = data.get('suhu_udara', 0)
        humi = data.get('kelembapan_udara', 0)
        tanah = data.get('kelembapan_tanah', 0)
        
        # Update status pompa (agar UI sinkron dengan kondisi lapangan)
        if 'pompa_status' in data:
            LAST_PUMP_STATUS = data['pompa_status']

        # 2. Ambil data Rainfall dari API WeatherAPI
        hujan_api = get_rainfall_from_api()

        # 3. Simpan Semua ke Database
        with app.app_context():
            new_data = SensorData(
                soil_moisture=tanah,
                humidity=humi,
                temperature=suhu,
                rainfall=hujan_api  # Data dari API masuk sini
            )
            db.session.add(new_data)
            db.session.commit()
            print(f"--> Data Saved. Tanah: {tanah}%, Hujan (API): {hujan_api} mm")

    except Exception as e:
        print("Error memproses MQTT:", e)
# ==========================================
# RUTE HALAMAN WEB
# ==========================================

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/status')
def status():
    esp_status = "Unknown"
    last_seen_time = None
    
    latest_data = SensorData.query.order_by(SensorData.timestamp.desc()).first()
    
    if latest_data:
        last_seen_time = latest_data.timestamp
        time_diff = (datetime.utcnow() - last_seen_time).total_seconds()
        esp_status = "Offline" if time_diff > ESP_OFFLINE_THRESHOLD else "Online"
    
    page = request.args.get('page', 1, type=int)
    pagination = SensorData.query.order_by(SensorData.timestamp.desc()).paginate(page=page, per_page=15, error_out=False)
    
    return render_template('status.html', esp_status=esp_status, last_seen_time=last_seen_time, pagination=pagination)

# ==========================================
# API UNTUK FRONTEND (JAVASCRIPT CHART)
# ==========================================

@app.route('/api/latest-status')
def get_latest_status():
    # Ambil data terakhir dari DB untuk ditampilkan di Dashboard
    latest_data = SensorData.query.order_by(SensorData.timestamp.desc()).first()
    
    # Siapkan JSON, handle jika DB masih kosong
    if latest_data:
        data_json = latest_data.to_dict()
    else:
        data_json = {"soil_moisture": 0, "humidity": 0, "temperature": 0, "rainfall": 0}
    
    return jsonify({
        "sensor_data": data_json,
        "pump_status": {"state": LAST_PUMP_STATUS} 
    })

@app.route('/api/chart-data')
def get_chart_data():
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

@app.route('/irrigate', methods=['POST'])
def manual_irrigate():
    """
    Mengirim trigger 'MANUAL' ke ESP32.
    ESP32 akan menyalakan pompa selama 2 detik lalu mati sendiri.
    """
    msg = "MANUAL" 
    
    # Publish ke topik yang didengarkan ESP32
    mqtt.publish('kebun/pompa', msg)
    print(f"PERINTAH MANUAL: Mengirim '{msg}' ke topik 'kebun/pompa'")
    
    return jsonify({
        "message": "Menyiram tanaman (2 Detik)...", 
        "state": "ON" 
    }), 200

# ==========================================
# RUTE REST API (KOMENTAR/NONAKTIF)
# ==========================================
# Route ini dimatikan karena data sekarang masuk lewat MQTT

# @app.route('/data', methods=['POST'])
# def receive_data():
#     if request.is_json:
#         data = request.get_json()
#         try:
#             new_data = SensorData(
#                 soil_moisture=data['soil_moisture'],
#                 humidity=data['humidity'],
#                 temperature=data['temperature'],
#                 rainfall=data['rainfall']
#             )
#             db.session.add(new_data)
#             db.session.commit()
#             return jsonify({"message": "Data berhasil diterima!"}), 201
#         except Exception as e:
#             db.session.rollback(); return jsonify({"error": str(e)}), 500
#     return jsonify({"error": "Request harus dalam format JSON"}), 400


# ==========================================
# MAIN PROGRAM
# ==========================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
       
            
    # use_reloader=False disarankan saat menggunakan MQTT Client agar tidak double connect
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)