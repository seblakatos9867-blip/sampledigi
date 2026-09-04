#include <Servo.h>

const int SWITCH_PIN = 2;   // Micro switch
const int SERVO_PIN  = 9;   // Servo that tilts the flap
const int LED_PIN    = 13;  // DRS active indicator

const int FLAP_DOWN_ANGLE = 0;
const int FLAP_UP_ANGLE   = 45;

Servo flapServo;

void setup() {
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);

  flapServo.attach(SERVO_PIN);
  flapServo.write(FLAP_DOWN_ANGLE);
}

void loop() {
  // Switch pressed = LOW → wing goes UP
  if (digitalRead(SWITCH_PIN) == LOW) {
    flapServo.write(FLAP_DOWN_ANGLE);
    digitalWrite(LED_PIN, HIGH);
  } else {
    flapServo.write(FLAP_UP_ANGLE);
    digitalWrite(LED_PIN, LOW);
  }

  delay(20);
}
