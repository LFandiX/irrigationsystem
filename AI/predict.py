import joblib  # joblib sering lebih efisien untuk model scikit-learn/lightgbm
import pandas as pd
import numpy as np

# 1. Tentukan nama file model Anda
nama_file_model = 'final_model.pkl'

try:
    # 2. Muat model dari file .pkl
    model = joblib.load(nama_file_model)
    print(f"Model '{nama_file_model}' berhasil dimuat.")
    print(f"Tipe model: {type(model)}")

    # 3. Siapkan data baru untuk diprediksi
    # PENTING: Nama kolom harus sama persis dan dalam urutan yang benar
    # Ini hanya CONTOH DATA, ganti dengan data Anda yang sebenarnya.


    data_baru = {
        'Soil_Moisture': [0.5],  # Ganti dengan nilai Anda
        'Temperature': [30.2],  # Ganti dengan nilai Anda
        '_Soil_Humidity': [2.0], # Ganti dengan nilai Anda
        'Air_temperature_(C)': [44.1], # Ganti dengan nilai Anda
        'Air_humidity_(%)': [20.5]   # Ganti dengan nilai Anda
    }

    # Buat DataFrame pandas dari data baru
    data_untuk_prediksi = pd.DataFrame(data_baru)

    print("\nData baru yang akan diprediksi:")
    print(data_untuk_prediksi)

    # 4. Lakukan prediksi
    # .predict() akan memberikan hasil kelas (misal: 0 atau 1, 'ya' atau 'tidak')
    hasil_prediksi = model.predict(data_untuk_prediksi)

    print(f"\n--- Hasil Prediksi ---")
    print(hasil_prediksi)

    # 5. (Opsional) Dapatkan probabilitas prediksi
    # .predict_proba() memberikan probabilitas untuk setiap kelas
    if hasattr(model, "predict_proba"):
        probabilitas_prediksi = model.predict_proba(data_untuk_prediksi)
        print(f"\n--- Probabilitas Prediksi ---")
        print(probabilitas_prediksi)

except FileNotFoundError:
    print(f"ERROR: File '{nama_file_model}' tidak ditemukan.")
    print("Pastikan file tersebut berada di direktori yang sama dengan script Anda.")
except Exception as e:
    print(f"Terjadi error: {e}")
    print("Pastikan semua library (joblib, pandas, lightgbm) sudah terinstal.")