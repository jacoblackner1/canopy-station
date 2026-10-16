/*
  Canopy station — Arduino Nano
  Moisture A0, light A1, pump relay D8, review/grow light D9.

  Relay is inverted: HIGH = pump ON, LOW = pump OFF.
  setup() holds D8 LOW so the pump stays off at boot.
  Cut hot only. COM + NO. Leave NC empty.

  Prints analogRead 0–1023. The Pi maps that to % using station.json.
  First analog read after a mux switch is discarded (A0/A1 crosstalk).
  After lamp/pump commands, wait so the 5V rail can settle.

  PUMP FAILSAFES (the Nano no longer trusts the Pi to turn the pump off):
    1. Hard max on-time: the pump is forced off after PUMP_MAX_MS no matter
       what the Pi says or doesn't say.
    2. Timed pulses: "WATER_MS:<ms>" runs the pump for <ms> (capped at
       PUMP_MAX_MS) and the Nano turns it off itself.
    3. Serial heartbeat: while the pump is on, if no line arrives from the Pi
       for HEARTBEAT_TIMEOUT_MS the pump is forced off (Pi crash / USB pulled).
       The Pi sends "PING" about once a second.
    4. AVR hardware watchdog (2 s): if this sketch hangs, the chip resets and
       setup() drives the pump pin LOW again.
    5. Lockout: after a forced stop the pump refuses WATER_* until the Pi
       sends "RESET_FAULT" (so a looping bug can't keep restarting it).
  Status line: MOISTURE:<n>|LIGHT:<n>|PUMP:<0/1>|FAULT:<code>
    FAULT codes: 0 none, 1 max on-time hit, 2 heartbeat lost, 3 watchdog reset.

  NOTE: old-bootloader Nano clones can boot-loop on a watchdog reset.
  Use the "ATmega328P" (new/Optiboot) board option, or burn Optiboot,
  before relying on failsafe 4.
*/

#include <avr/wdt.h>

// Reset cause, captured before main(). Optiboot clears MCUSR before jumping
// to the sketch and hands the original value over in r2, so reading MCUSR in
// setup() alone never saw the watchdog flag (FAULT:3 could never fire).
// Also disables the WDT as early as possible so a watchdog reset can't
// re-trigger while the C runtime initialises.
uint8_t resetCause __attribute__((section(".noinit")));
void captureResetCause(void) __attribute__((naked, used, section(".init3")));
void captureResetCause(void) {
  // Naked function: no stack frame, so no locals. Store r2 directly.
  __asm__ __volatile__("sts %0, r2" : "=m"(resetCause));
  if (MCUSR) {
    resetCause = MCUSR;  // no bootloader / old bootloader: MCUSR is intact
  }
  MCUSR = 0;
  wdt_disable();
}

const int PIN_MOISTURE = A0;
const int PIN_LIGHT = A1;
const int PIN_PUMP = 8;
const int PIN_LAMP = 9;

const unsigned long PUMP_MAX_MS = 10000UL;          // absolute ceiling per run
const unsigned long HEARTBEAT_TIMEOUT_MS = 3000UL;  // pump-on only

String cmdBuf;
bool pumpOn = false;
unsigned long pumpStartMs = 0;
unsigned long pumpRunMs = 0;
unsigned long lastRxMs = 0;
bool pumpLegacy = false;  // started by WATER_ON (no length given)
uint8_t fault = 0;

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

void pumpOff() {
  digitalWrite(PIN_PUMP, LOW);
  pumpOn = false;
}

bool pumpStart(unsigned long ms) {
  if (fault != 0) {
    return false;
  }
  if (ms == 0 || ms > PUMP_MAX_MS) {
    ms = PUMP_MAX_MS;
  }
  pumpRunMs = ms;
  pumpStartMs = millis();
  lastRxMs = pumpStartMs;
  pumpOn = true;
  digitalWrite(PIN_PUMP, HIGH);
  return true;
}

void setup() {
  // Pump pin first so it is LOW as early as possible after any reset.
  digitalWrite(PIN_PUMP, LOW);
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_LAMP, OUTPUT);
  digitalWrite(PIN_LAMP, LOW);
  if (resetCause & _BV(WDRF)) {
    fault = 3;
  }
  Serial.begin(9600);
  cmdBuf.reserve(32);
  wdt_enable(WDTO_2S);
}

bool handleCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd == "PING") {
    return false;
  }
  if (cmd == "WATER_ON") {
    // Legacy: still bounded by PUMP_MAX_MS and the heartbeat.
    bool ok = pumpStart(PUMP_MAX_MS);
    pumpLegacy = ok;
    return ok;
  }
  if (cmd.startsWith("WATER_MS:")) {
    long ms = cmd.substring(9).toInt();
    if (ms <= 0) {
      return false;
    }
    pumpLegacy = false;
    return pumpStart((unsigned long)ms);
  }
  if (cmd == "WATER_OFF") {
    pumpOff();
    return true;
  }
  if (cmd == "RESET_FAULT") {
    pumpOff();
    fault = 0;
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

void checkPump() {
  if (!pumpOn) {
    return;
  }
  unsigned long now = millis();
  if (now - pumpStartMs >= pumpRunMs) {
    // Normal end of a timed pulse; only a fault if we hit the hard ceiling.
    bool ceiling = pumpLegacy;
    pumpOff();
    if (ceiling) {
      fault = 1;
    }
    return;
  }
  if (now - lastRxMs >= HEARTBEAT_TIMEOUT_MS) {
    pumpOff();
    fault = 2;
  }
}

void loop() {
  wdt_reset();
  bool acted = false;
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdBuf.length() > 0) {
        lastRxMs = millis();
        if (handleCommand(cmdBuf)) {
          acted = true;
        }
        cmdBuf = "";
      }
    } else if (cmdBuf.length() < 30) {
      cmdBuf += c;
    }
  }
  checkPump();
  if (acted) {
    delay(80);
  }

  int moisture = readPin(PIN_MOISTURE);
  int light = readPin(PIN_LIGHT);
  Serial.print("MOISTURE:");
  Serial.print(moisture);
  Serial.print("|LIGHT:");
  Serial.print(light);
  Serial.print("|PUMP:");
  Serial.print(pumpOn ? 1 : 0);
  Serial.print("|FAULT:");
  Serial.println(fault);

  // Split the 200 ms idle so pump checks stay responsive (~50 ms).
  for (int i = 0; i < 4; i++) {
    delay(50);
    checkPump();
  }
}
