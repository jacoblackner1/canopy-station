/*
  Canopy station — Arduino Nano
  Moisture A0, light A1, pump relay D8, review/grow light D9.

  Relay is inverted: HIGH = pump ON, LOW = pump OFF.
  setup() holds D8 LOW so the 120V pump stays off at boot.
  Cut hot only. COM + NO. Leave NC empty.

  analogRead is 0–1023. We map that to 0–100 so the Pi calibration
  (moisture dry 49 / wet 21, light dark 73 / daylight 10) matches.
*/

const int PIN_MOISTURE = A0;
const int PIN_LIGHT = A1;
const int PIN_PUMP = 8;
const int PIN_LAMP = 9;

String cmdBuf;

int readAvg(int pin) {
  long sum = 0;
  for (int i = 0; i < 4; i++) {
    sum += analogRead(pin);
  }
  return (int)(sum / 4);
}

void setup() {
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_LAMP, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_LAMP, LOW);
  Serial.begin(9600);
  cmdBuf.reserve(32);
}

void handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
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

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdBuf.length() > 0) {
        handleCommand(cmdBuf);
        cmdBuf = "";
      }
    } else if (cmdBuf.length() < 30) {
      cmdBuf += c;
    }
  }

  int moisture = map(readAvg(PIN_MOISTURE), 0, 1023, 0, 100);
  int light = map(readAvg(PIN_LIGHT), 0, 1023, 0, 100);
  Serial.print("MOISTURE:");
  Serial.print(moisture);
  Serial.print("|LIGHT:");
  Serial.println(light);
  delay(200);
}
