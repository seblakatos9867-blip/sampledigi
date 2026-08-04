# DRS System — Wiring Guide (Arduino Uno)

## Components

| Component | Purpose |
|-----------|---------|
| Arduino Uno | Main controller |
| Servo motor (SG90 or MG996R) | Tilts the wing flap |
| Hall-effect sensor (A3144 or similar) | Measures wheel speed |
| Analog wind/pressure sensor | Detects airflow on the wing |
| LED | DRS active indicator |
| Magnet (small, glued to wheel) | Triggers the Hall sensor each revolution |

## Wiring

### Servo Motor
- Signal (orange/white) → Pin 9
- VCC (red) → 5V
- GND (brown/black) → GND

### Hall-Effect Speed Sensor
- OUT → Pin 2 (interrupt pin)
- VCC → 5V
- GND → GND

### Wind / Pressure Sensor (analog output)
- Signal → A0
- VCC → 5V
- GND → GND

### Status LED
- Anode (+) → Pin 13 (through 220Ω resistor)
- Cathode (−) → GND

## Tuning

Edit these constants in `drs_system.ino` to match your setup:

| Constant | Default | Description |
|----------|---------|-------------|
| `SPEED_THRESHOLD_KMH` | 60.0 | Speed (km/h) above which DRS opens |
| `WIND_THRESHOLD_RAW` | 512 | Analog reading (0–1023) to trigger DRS |
| `WHEEL_CIRCUMFERENCE_M` | 1.8 | Your wheel's circumference in meters |
| `MAGNETS_PER_REV` | 1 | Number of magnets on the wheel |
| `WING_DOWN_ANGLE` | 0 | Servo angle when wing is closed |
| `WING_UP_ANGLE` | 45 | Servo angle when wing is open |
