# Screensaver controller

The screensaver controller is a Python script essentially vibe coded using ChatGPT. It's the part of this effort that has taken the most time so far. It has two functions:

* Display pictures when the kiosk has not had any touch inputs for 5 minutes.
* Turn off the display when the room is dark.
* Capture (eat) the first touch when pictures are displayed and stop the display so control cah return to the kiosk page.

One key element is that the Python script must consume the touch that causes return to the kiosk or the touch will pass through to the kiosk and could result in an unwanted action.

The "turn off when dark" feature requires some additional planning. It will be implemented by creating a separate process (to run in the same host) that will monitor lighting and publish messages when lighting conditinos change and on a timed basis. In other words, at a minimum of a specified time period such as 15 minutes and more frequently if ilghting level changes. This process will publish lighting measurements using MQTT and the topic will be the standard `HA/[hostname]/[location]/[measurement]` and in this case and with the system running on a host named `kiosk` the topic will be `HA/kiosk/kiosk/lighting`. The light level will be normalized to a scale from 0 to 100 representing "none-detectable" to "maximum-measurable". (These could be adjusted if needed as the range needed for this application is well within those limits.) The Payload will be in JSON format and will include:

* `t` timestamp (UNIX time_t)
* `level` light level.
* `device` Sensor used to make measurement.

Other interesting parameters such as uptime or WiFi signal strength could be added to the payload as desired. The above are the minimum. A typical message as viewed using `mosquitto_sub -v -t HA/kiosk/kiosk/lighting` could look like:

```text
HA/kiosk/kiosk/lighting {"t":1792010217, "level":47, "device":"VEML7700" }
```

The python script will implement hysterysis and timing when deciding there has been a change.

Test MQTT messages can be generated using the following:

```text
mosquitto_pub -h pilog3b \
    -t HA/kiosk/kiosk/lighting \
    -m "{\"t\":$(date +%s),\"level\":47,\"device\":\"TEST\"}"
```