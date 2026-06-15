#include "DHT.h"

// Define the digital pin connected to the DHT sensor
// Pin 2 is a common choice for Arduino Uno
#define DHTPIN 2     

// Uncomment whatever type you're using!
// #define DHTTYPE DHT11   // DHT 11
#define DHTTYPE DHT22   // DHT 22  (AM2302), AM2321
// #define DHTTYPE DHT21   // DHT 21 (AM2301)

// Initialize DHT sensor.
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  // Start the serial connection with 9600 baud rate
  // This must match the backend's settings (sensor_baud_rate=9600)
  Serial.begin(9600);
  
  // Wait for serial monitor to open (optional)
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }

  // Initialize the DHT sensor
  dht.begin();
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

  // Check if any reads failed and exit early (to try again).
  if (isnan(humidity) || isnan(temperature)) {
    // We do not print anything if reading fails, to prevent 
    // sending malformed data to the Python backend.
    return;
  }

  // Send the payload to the backend via Serial.
  // Expected format by backend: TEMP:26.5,HUM:72.3
  Serial.print("TEMP:");
  Serial.print(temperature, 1);
  Serial.print(",HUM:");
  Serial.print(humidity, 1);
  Serial.println();
}
