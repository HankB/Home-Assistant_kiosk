# Screensaver controller

The screensaver controller is a Python script essentially vibe coded using ChatGPT. It's the part of this effort that has taken the most time so far. It has two functions:

* Display pictures when the kiosk has not had any touch inputs for 5 minutes.
* Capture (eat) the first touch when pictures are displayed and stop the display so control cah return to the kiosk page.

One key element is that the Python script must consume the touch that causes return to the kiosk or the touch will pass through to the kiosk and could result in an unwanted action.

I hope to implement a feature that will turn the screen off when the room is dark and presumably no one is present to see the pictures.
