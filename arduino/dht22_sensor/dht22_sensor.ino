#include "DHT.h"
#include <math.h>

// Define the digital pin connected to the DHT sensor
// Pin 2 is a common choice for Arduino Uno
#define DHTPIN 4

// Uncomment whatever type you're using!
// #define DHTTYPE DHT11   // DHT 11
#define DHTTYPE DHT22 // DHT 22  (AM2302), AM2321
// #define DHTTYPE DHT21   // DHT 21 (AM2301)

// Calibration offsets against a reference thermometer/hygrometer.
// Leave at 0.0f when calibrating on the backend via SENSOR_TEMP_OFFSET / SENSOR_HUMIDITY_OFFSET.
const float TEMP_OFFSET_C = 0.0f;
const float HUM_OFFSET_PCT = 0.0f;

// DHT22 physical operating limits per datasheet.
const float DHT22_TEMP_MIN_C = -40.0f;
const float DHT22_TEMP_MAX_C = 80.0f;
const float DHT22_HUM_MIN_PCT = 0.0f;
const float DHT22_HUM_MAX_PCT = 100.0f;

// Sliding-window trimmed-mean smoothing and spike suppression.
const int SAMPLE_WINDOW = 5;
const float MAX_TEMP_STEP_C = 4.0f;
const float MAX_HUM_STEP_PCT = 15.0f;
const int SPIKE_CONFIRM_COUNT = 3;

float tempWindow[SAMPLE_WINDOW];
float humWindow[SAMPLE_WINDOW];
int windowCount = 0;
int windowHead = 0;
bool hasBaseline = false;
float lastSmoothedTemp = 0.0f;
float lastSmoothedHum = 0.0f;
int consecutiveSpikes = 0;

// Initialize DHT sensor.
DHT dht(DHTPIN, DHTTYPE);

static float clampFloat(float value, float minVal, float maxVal) {
  if (value < minVal) return minVal;
  if (value > maxVal) return maxVal;
  return value;
}

static float trimmedMean(const float *samples, int count) {
  float sorted[SAMPLE_WINDOW];
  for (int i = 0; i < count; i++) {
    sorted[i] = samples[i];
  }
  for (int i = 1; i < count; i++) {
    float key = sorted[i];
    int j = i - 1;
    while (j >= 0 && sorted[j] > key) {
      sorted[j + 1] = sorted[j];
      j--;
    }
    sorted[j + 1] = key;
  }
  if (count >= 3) {
    float sum = 0.0f;
    for (int i = 1; i < count - 1; i++) {
      sum += sorted[i];
    }
    return sum / (count - 2);
  }
  float sum = 0.0f;
  for (int i = 0; i < count; i++) {
    sum += sorted[i];
  }
  return sum / count;
}

static void pushSample(float temp, float hum) {
  tempWindow[windowHead] = temp;
  humWindow[windowHead] = hum;
  windowHead = (windowHead + 1) % SAMPLE_WINDOW;
  if (windowCount < SAMPLE_WINDOW) {
    windowCount++;
  }
}

void setup() {
  // Start the serial connection with 9600 baud rate
  // This must match the backend's settings (sensor_baud_rate=9600)
  Serial.begin(9600);

  // Wait for serial monitor to open (optional)
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }

  // Initialize the DHT sensor and allow power-on stabilization
  dht.begin();
  delay(2000);
}

void loop() {
  // Wait 2 seconds between measurements.
  // The DHT22 sensor can only be read every 2 seconds.
  delay(2000);

  // Reading temperature or humidity takes about 250 milliseconds!
  // Sensor readings may also be up to 2 seconds 'old' (its a very slow sensor)
  float humidity = dht.readHumidity();
  // Read temperature as Celsius (the default)
  float temperature = dht.readTemperature();

  // Check if any reads failed or returned non-finite / out-of-range values.
  if (isnan(humidity) || isnan(temperature) || isinf(humidity) || isinf(temperature)) {
    Serial.println("ERROR: Failed to read from DHT sensor! (Check wiring, pin, "
                   "or DHTTYPE)");
    return;
  }
  if (temperature < DHT22_TEMP_MIN_C || temperature > DHT22_TEMP_MAX_C ||
      humidity < DHT22_HUM_MIN_PCT || humidity > DHT22_HUM_MAX_PCT) {
    Serial.println("ERROR: Out-of-range DHT22 reading discarded");
    return;
  }

  temperature = clampFloat(temperature + TEMP_OFFSET_C, DHT22_TEMP_MIN_C, DHT22_TEMP_MAX_C);
  humidity = clampFloat(humidity + HUM_OFFSET_PCT, DHT22_HUM_MIN_PCT, DHT22_HUM_MAX_PCT);

  // Guard against transient electrical spikes once warmed up; confirm real shifts after 3 reads.
  if (hasBaseline && windowCount >= 3) {
    bool largeJump = fabs(temperature - lastSmoothedTemp) > MAX_TEMP_STEP_C ||
                     fabs(humidity - lastSmoothedHum) > MAX_HUM_STEP_PCT;
    if (largeJump) {
      consecutiveSpikes++;
      if (consecutiveSpikes < SPIKE_CONFIRM_COUNT) {
        return;
      }
      windowCount = 0;
      windowHead = 0;
    }
  }
  consecutiveSpikes = 0;

  pushSample(temperature, humidity);
  lastSmoothedTemp = trimmedMean(tempWindow, windowCount);
  lastSmoothedHum = clampFloat(trimmedMean(humWindow, windowCount), DHT22_HUM_MIN_PCT, DHT22_HUM_MAX_PCT);
  hasBaseline = true;

  // Send the smoothed payload to the backend via Serial.
  // Expected format by backend: TEMP:26.50,HUM:72.30
  Serial.print("TEMP:");
  Serial.print(lastSmoothedTemp, 2);
  Serial.print(",HUM:");
  Serial.print(lastSmoothedHum, 2);
  Serial.println();
}
  