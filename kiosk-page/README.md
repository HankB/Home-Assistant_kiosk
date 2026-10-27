# Kiosk page

This page was developed substantially with ChatGPT and is likely the one that could most easily be replaced by the plethora of other efforts. It is also most likely the one least portable to any other project as it displays entities specific to my installation. Development was performed on a desktop with much larger screen + keyboard and mouse and results were viewed on the Pi/touchscreen.

Central to the display and at top left is a color coded report of Comed (utility) 5 minute price averages. We get a price benefit by avoiding high demand periods and this provides a convenient way to provide access. Everything else is more or less an afterthought including control of some smart switches and lights and some status updates such as freezer temperature and garage door position.

Apparently it was not posible to construct the kiosk page using the GUI (except to edit the YAML directly.) One purpose of this repo is to have a place (other than my personal notes) to keep an up to date copy of the YAML. It is copied directly into the HASS GUI and not stored in its own file. A local copy is named [kiosk.yaml](./kiosk.yaml)

The kiosk Lovelace page is in it's own dashboard so the HACS extension `kiosk mode` can be applied. It works for all pages in a dashboard and was not needed for the other pages in the "Overview" dashboard.

## Creating the Dashboard and kiosk page

This was not intuitively obvious to me so I'm repeating instructions here in detail. You will need administrative rights on the Home Assistant instance.

To create the new dashboard and empty view:

1. Click the "Edit Dashboard" (pencil icon) in the upper right corner.
2. Click the three dot menu upper right and select "Manage Dashboards"
3. Clock the blue "+ Add dashboard" button on the lower left.
4. Select "New dashboard from scratch"
5. Provide a useful title such as "kiosk-dashboard" and choose an icon. I left the URL "kiosk-dashboard".
6. Admin-only off.
7. Add to sidebar on.
8. Clock "Create"
9. Return to the Overview and choose "kiosk-dashboard" from the list of available dashboards.

To enter the YAML code:

1. Click the "Edit Dashboard" (pencil icon) in the upper right corner. (Note: Once yuo enable the HACS "kiosk mode" it is necessary to temporarily add `?disable_km` to the end of the URL to reveal this menu bar.)
2. Click the three dot menu and select "Raw Configuration Editor" 
3. Replace the YAML in the edit view with the configuration for your dashboard.
4. Click "Save" and click the 'X' in the upper left to close the edit.

Inspect the page and declare victory at this point! (I still have work to do with this.)
