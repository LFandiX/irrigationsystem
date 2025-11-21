-- SQLite
DELETE FROM sensor_data WHERE temperature > 25;

INSERT INTO sensor_data (temperature, humidity, soil_moisture,rainfall, timestamp) VALUES (1, 30, 70, 10, '2024-06-01 10:00:00');


SELECT * FROM sensor_data;