/*
  Canopy station — Arduino Nano
  Moisture A0, light A1, pump relay D8, review/grow light D9.

  Relay is inverted: HIGH = pump ON, LOW = pump OFF.
  setup() holds D8 LOW so the 120V pump stays off at boot.
  Cut hot only. COM + NO. Leave NC empty.

  Prints analogRead 0–1023. The Pi maps that to % using station.json.
  First analog read after a mux switch is discarded (A0/A1 crosstalk).
  After lamp/pump commands, wait so the 5V rail can settle.
*/

const int PIN_MOISTURE = A0;
const int PIN_LIGHT = A1;
const int PIN_PUMP = 8;
const int PIN_LAMP = 9;

String cmdBuf;

int readPin(int pin) {
  analogRead(pin);
  delayMicroseconds(400);
  int v[5];
  for (int i = 0; i < 5; i++) {
    v[i] = analogRead(pin);
    delayMicroseconds(120);
  }
  for (int i = 1; i < 5; i++) {
    int key = v[i];
    int j = i;
    while (j > 0 && v[j - 1] > key) {
      v[j] = v[j - 1];
      j--;
    }
    v[j] = key;
  }
  return v[2];
}

void setup() {
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_LAMP, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_LAMP, LOW);
  Serial.begin(9600);
  cmdBuf.reserve(32);
}

bool handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "WATER_ON") {
    digitalWrite(PIN_PUMP, HIGH);
    return true;
  }
  if (cmd == "WATER_OFF") {
    digitalWrite(PIN_PUMP, LOW);
    return true;
  }
  if (cmd == "LIGHT_ON") {
    digitalWrite(PIN_LAMP, HIGH);
    return true;
  }
  if (cmd == "LIGHT_OFF") {
    digitalWrite(PIN_LAMP, LOW);
    return true;
  }
  return false;
}

void loop() {
  bool acted = false;
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdBuf.length() > 0) {
        if (handleCommand(cmdBuf)) {
          acted = true;
        }
        cmdBuf = "";
      }
    } else if (cmdBuf.length() < 30) {
      cmdBuf += c;
    }
  }
  if (acted) {
    delay(80);
  }

  int moisture = readPin(PIN_MOISTURE);
  int light = readPin(PIN_LIGHT);
  Serial.print("MOISTURE:");
  Serial.print(moisture);
  Serial.print("|LIGHT:");
  Serial.println(light);
  delay(200);
}
