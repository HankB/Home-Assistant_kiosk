# Kiosk page

This page was developed substantially with ChatGPT and is liely the one that could most easily be replaced by the plethora of other efforts. It is also most likely the one least portable to any other project as it displays entities specific to my installation.

Central to the display and at top left is a color coded report of Comed (utility) 5 minute price averages. We get a price benefit by avoiding high demand periods and this provides a convenient way to provide access. Everything else is more or less an afterthought including control of some smart switches and lights and some status updates such as freezer temperature and garage door position.

Apparently it was not posible to construct the kiosk page using the GUI (except to edit the YAML directly.) One purpose of this repo is to have a place (other than my personal notes) to keep an up to date copy of the YAML. It is copied directly into the HASS GUI and not stored in its own file but is named [kiosk.yaml](./kiosk.yaml)

The kiosk Lovelace page is in it's own dashboard so the HACS extension `kiosk mode` can be applied. It works for all pages in a dashboard and was not needed for the other pages in the 