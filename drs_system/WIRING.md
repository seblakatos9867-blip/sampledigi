# DRS System — Wiring Guide (Arduino Uno)

## Components

| Component | Purpose |
|-----------|---------|
| Arduino Uno | Main controller |
| Servo motor (SG90 or MG996R) | Tilts the flap |
| Micro switch | Triggers DRS when pressed |
| LED | DRS active indicator |

## Wiring

### Micro Switch
- One leg → Pin 2
- Other leg → GND
- (Uses internal pull-up resistor, no external resistor needed)

### Servo Motor
- Signal (orange/white) → Pin 9
- VCC (red) → 5V
- GND (brown/black) → GND

### Status LED
- Anode (+) → Pin 13 (through 220Ω resistor)
- Cathode (−) → GND

## Tuning

| Constant | Default | Description |
|----------|---------|-------------|
| `FLAP_DOWN_ANGLE` | 0 | Servo angle when flap is closed |
| `FLAP_UP_ANGLE` | 45 | Servo angle when flap is open |
