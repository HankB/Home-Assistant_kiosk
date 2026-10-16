# Home-Assistant_kiosk

Produce a Home Assistant kiosk running on a Pi 3B displaying on the original 7" touchscreen display.

## Motivation

I have an idle Pi 3B and a 7" (original) touchscreen that I thought would be a reasonable basis for a useful kiosk display for my Home Assistant installation.

## AI/LLM warning

If you object to the use of AI/LLMs for system development, you won't like this. I worked with two LLMs.

* Google Search (AFAIK, Gemini.) I went as far as configuring the color coded Comed price indicator. I was getting so many wrong answers and finally started looping on wrong answers so I moved on to ChatGPT. (I can't find this conversation in the list of Gemini conversations so maybe it's not really Gemini.)
* ChatGPT, for which I upgraded to the free trial of "Plus."

## Plans and features

These grew organically during the process. Once a first screen was realized I found that this display is subject to burn in. We implemented screen blanking. Then I looked at the blank screen and thought that a rotating picture display would be better. Now I'm looking at the display before I turn in for the night and I think that it should go dark when ambient is dark. And so it goes.

The features fall into three areas at present:

* Configuration of a page suitable for a small 800x400 display and which includes the information most important to me. This is a YAML configuratoin page and will be found in `./yaml/`
* Configuration of the web browser to take the full screen for the Kiosk page.
* Configuration of screen blanking and a rotating picture display.

## Status

* 2026-10-15 program to publish ambient light values.
* 2026-10-14 Turn off display when dark implemented.
* 2026-10-13 (as of) kiosk screen roughed out.
* 2026-10-13 (as of) screen saver/picture display working.
* 2026-10-13 (as of) kiosk configuration of browser mostly working.

* [Kiosk page notes](kiosk-page/README.md)
* [Browser notes](browser/README.md)
* [Screen saver notes](screensaver/README.md)
* [VEML7700 ambient light sensor publisher](https://github.com/HankB/veml7700-mqtt/tree/main)
