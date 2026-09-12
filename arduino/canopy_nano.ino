/*
  Canopy station — Arduino Nano
  Moisture A0, light A1, pump relay D8, review/grow light D9.

  Relay is inverted: HIGH = pump ON, LOW = pump OFF.
  setup() holds D8 LOW so the 120V pump stays off at boot.
  Cut hot only. COM + NO. Leave NC empty.
*/

const int PIN_MOISTURE = A0;
const int PIN_LIGHT = A1;
const int PIN_PUMP = 8;
const int PIN_LAMP = 9;

void setup() {
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_LAMP, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_LAMP, LOW);
  Serial.begin(9600);
}

void loop() {
  int moisture = analogRead(PIN_MOISTURE);
  int light = analogRead(PIN_LIGHT);
  Serial.print("MOISTURE:");
  Serial.print(moisture);
  Serial.print("|LIGHT:");
  Serial.println(light);

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "WATER_ON") {
      digitalWrite(PIN_PUMP, HIGH);
    } else if (cmd == "WATER_OFF") {
      digitalWrite(PIN_PUMP, LOW);
    } else if (cmd == "LIGHT_ON") {
      digitalWrite(PIN_LAMP, HIGH);
    } else if (cmd == "LIGHT_OFF") {
      digitalWrite(PIN_LAMP, LOW);
    }
  }

  delay(200);
}
