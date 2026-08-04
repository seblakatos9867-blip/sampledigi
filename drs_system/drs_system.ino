#include <Servo.h>

// ── Pin assignments ──
const int SPEED_SENSOR_PIN = 2;   // Hall-effect speed sensor (interrupt-capable)
const int WIND_SENSOR_PIN  = A0;  // Analog anemometer / wind pressure sensor
const int SERVO_PIN        = 9;   // Servo that tilts the wing
const int LED_PIN          = 13;  // Status LED (DRS active indicator)

// ── Thresholds (tune these for your setup) ──
const float SPEED_THRESHOLD_KMH  = 60.0;  // DRS opens above this speed
const int   WIND_THRESHOLD_RAW   = 512;   // Analog reading (0-1023) to trigger DRS

// ── Wing angles ──
const int WING_DOWN_ANGLE = 0;    // Wing closed (max downforce)
const int WING_UP_ANGLE   = 45;   // Wing open (reduced drag)

// ── Speed calculation ──
const float WHEEL_CIRCUMFERENCE_M = 1.8;  // Wheel circumference in meters
const int   MAGNETS_PER_REV       = 1;    // Magnets on the wheel for the Hall sensor

// ── Objects & state ──
Servo wingServo;

volatile unsigned long pulseCount    = 0;
unsigned long          lastSpeedCalc = 0;
const unsigned long    SPEED_CALC_INTERVAL_MS = 500;

float currentSpeedKmh = 0.0;
int   currentWindRaw  = 0;
bool  drsActive       = false;

void setup() {
  Serial.begin(9600);

  pinMode(SPEED_SENSOR_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);

  wingServo.attach(SERVO_PIN);
  wingServo.write(WING_DOWN_ANGLE);

  attachInterrupt(digitalPinToInterrupt(SPEED_SENSOR_PIN), countPulse, FALLING);

  Serial.println("DRS System Initialized");
  Serial.println("----------------------");
  Serial.print("Speed threshold: ");
  Serial.print(SPEED_THRESHOLD_KMH);
  Serial.println(" km/h");
  Serial.print("Wind threshold:  ");
  Serial.println(WIND_THRESHOLD_RAW);
}

void loop() {
  unsigned long now = millis();

  // Calculate speed every SPEED_CALC_INTERVAL_MS
  if (now - lastSpeedCalc >= SPEED_CALC_INTERVAL_MS) {
    noInterrupts();
    unsigned long count = pulseCount;
    pulseCount = 0;
    interrupts();

    float revolutions = (float)count / MAGNETS_PER_REV;
    float distanceM   = revolutions * WHEEL_CIRCUMFERENCE_M;
    float timeSec     = SPEED_CALC_INTERVAL_MS / 1000.0;
    float speedMs     = distanceM / timeSec;
    currentSpeedKmh   = speedMs * 3.6;

    lastSpeedCalc = now;
  }

  // Read wind sensor
  currentWindRaw = analogRead(WIND_SENSOR_PIN);

  // DRS logic: activate if EITHER condition is met
  bool shouldActivate = (currentSpeedKmh >= SPEED_THRESHOLD_KMH) ||
                        (currentWindRaw >= WIND_THRESHOLD_RAW);

  if (shouldActivate && !drsActive) {
    activateDRS();
  } else if (!shouldActivate && drsActive) {
    deactivateDRS();
  }

  // Print telemetry
  printTelemetry();

  delay(100);
}

void countPulse() {
  pulseCount++;
}

void activateDRS() {
  drsActive = true;
  wingServo.write(WING_UP_ANGLE);
  digitalWrite(LED_PIN, HIGH);
  Serial.println(">>> DRS ACTIVATED <<<");
}

void deactivateDRS() {
  drsActive = false;
  wingServo.write(WING_DOWN_ANGLE);
  digitalWrite(LED_PIN, LOW);
  Serial.println(">>> DRS DEACTIVATED <<<");
}

void printTelemetry() {
  Serial.print("Speed: ");
  Serial.print(currentSpeedKmh, 1);
  Serial.print(" km/h | Wind: ");
  Serial.print(currentWindRaw);
  Serial.print(" | DRS: ");
  Serial.println(drsActive ? "OPEN" : "CLOSED");
}
