# TailWatch User Guide

Welcome to TailWatch — your window into the aircraft flying nearby. This guide will help you set up and use your wall-mounted display.

---

## What It Does

TailWatch is a wall display that shows one airplane flying near your location in real time. Each time you look, you see that plane's flight number, airline, route, current altitude, and speed — plus the city it's departing from or arriving at. The display updates every 15 seconds or so, and if a different, closer aircraft comes into view, the display smoothly switches to show that instead. If the skies are empty, it tells you `NO TRAFFIC`. It runs on its own after setup — no app, no subscription, no constant internet required (though it does need Wi-Fi for your home network to fetch live data).

---

## First-Time Setup

### Power On

Plug the USB cable into your home power adapter and connect it to the device. Within a few seconds, you'll see something happen on the screen.

### If Wi-Fi Works

If TailWatch can reach your home Wi-Fi, it will join automatically and display a flight card.

### If Wi-Fi Doesn't Connect

If TailWatch hasn't been set up before, or if it can't find your Wi-Fi, the screen will show:

```
WIFI SETUP
TailWatch-XXXX
pw xxxxxxxx
192.168.4.1
```

This is the device's own temporary Wi-Fi network (a "hotspot"), plus its password and web address. Here's how to use it:

1. On your phone, go to **Settings** > **Wi-Fi** and look for the network called `TailWatch-XXXX` (where `XXXX` are four random characters shown on the panel). Join it using the password shown on the screen.

2. Open a web browser and navigate to `192.168.4.1`. You'll see a settings page with a Wi-Fi form at the top.

3. Under "Network name (SSID)," enter your home Wi-Fi network name. Under "Password," enter your Wi-Fi password. If your network has no password, check the "Open network" box instead.

4. Tap **Save Wi-Fi & restart** at the bottom. TailWatch will restart and join your home network.

5. Go back to your phone's Wi-Fi settings and reconnect to your normal home network. TailWatch is now online.

If you get the network name or password wrong, or if your Wi-Fi is unreachable, TailWatch will come back up as the `TailWatch-XXXX` hotspot so you can try again. There's always a way to recover — you'll never be stuck.

---

## Setting Your Location

Once TailWatch is on your home network, you can open its settings page to tell it where you are.

1. On your phone or computer, find TailWatch's address: check your router's device list for its IP address (it looks like `192.168.x.x`), or check the serial output if you have it plugged into a computer. Visit that address in a web browser.

2. You'll see the settings page. Look for the **Latitude** and **Longitude** fields near the top, and enter your home's coordinates. (You can find these by searching your address on Google Maps — right-click and copy the numbers.)

3. Below that is a field called **Box (miles each way)**. This is your "search radius" — how far out to look for aircraft. The default is 10 miles in each direction, which means a 20-mile-wide box centered on your location. Adjust this to taste:
   - **5–10 miles** if you live near a busy airport — you'll see planes constantly.
   - **15–20 miles** if you live farther out — more variety, but longer waits between aircraft.
   - **25–50 miles** if you want to see even distant traffic.

4. Tap **Save** to store your settings.

After this, TailWatch will show aircraft that are within your box, closest to your location first.

---

## Customizing the Display

The settings page has several ways to personalize your experience.

### Brightness

You can set how bright the display is during the day, at night, and at maximum. Use the three sliders under **Brightness**:
- **Day**: How bright during daylight hours (try 0.60–0.80).
- **Night**: How bright after dark (try 0.15–0.30 so it doesn't light up your room).
- **Max cap**: The absolute ceiling — even in day mode, it won't exceed this.

### Night Mode

Under **Night mode**, choose one of three options:
- **Off**: Display stays at day brightness all the time.
- **Fixed hours**: Switch to night brightness at a specific time (e.g., 9:00 PM to 6:30 AM). Enter the times under **Night start** and **Night end**.
- **After local sunset**: Uses your location and the time of year to switch automatically after sunset each day.

Night mode only dims the display. To turn it completely off on a schedule, use **Sleep** instead.

### Sleep (Display Off)

If you want the display to go completely dark during certain hours (e.g., so it doesn't run all night), use the **Sleep** section:
- Check **Enable sleep**.
- Enter your sleep start and end times (e.g., 11:00 PM to 6:30 AM).

During sleep hours, the screen will be completely blank. Aircraft polling pauses too, saving power.

### Filters

Under **Filters**, you can hide certain types of aircraft:
- **Hide helicopters**: Removes medical, police, and private helicopters.
- **Hide general aviation**: Removes small private planes (single-engine Cessnas, etc.).
- **Hide military**: Removes military and government aircraft.

These are optional. If you uncheck them, you'll see all traffic.

### Time Zone

Under **Local time**, select your time zone from the dropdown. This is used for sleep and night-mode schedules. If you're in the US, also check **Apply US daylight saving** so the device adjusts automatically on the second Sunday in March and first Sunday in November. (Uncheck this if you live in Arizona, Hawaii, or outside the US.)

---

## Understanding the Screen

Most of the time, you'll see a flight card with the plane's details. But sometimes you'll see other messages — here's what they mean.

### NO TRAFFIC

The screen shows `NO TRAFFIC` when there are no aircraft in your search box at that moment, or they're all filtered out. This is completely normal. Come back in a minute or two and a new plane will likely appear.

### NO LINK

The screen shows `NO LINK` if TailWatch can't reach the aircraft data source. This usually happens temporarily — maybe your internet is down, or the data service is busy. TailWatch will keep retrying. The display is fine, and your settings are still saved. Wait a minute and check again.

---

## Moving or Changing Your Wi-Fi Network

If you move to a new home or change your Wi-Fi network name or password, you don't need to do anything special.

The next time TailWatch tries to connect and fails, it will automatically show the `WIFI SETUP` screen with the temporary hotspot name and password (just like the first-time setup). Simply join that hotspot, open `192.168.4.1`, and enter your new network details. No factory reset needed — everything else stays the same.

---

## The Secret Animation

Here's a fun easter egg: if you hold down the **DOWN** button on the device for 5 seconds, a colorful Nyan Cat animation will play across the screen for up to 90 seconds. To stop it early, just press either the **UP** or **DOWN** button again. The display will return to showing aircraft.

---

## Troubleshooting

### The screen is dark or blank

1. Check your **Sleep** settings. If sleep is enabled and the current time falls within the sleep window, the screen will be off. Either disable sleep or adjust the times.
2. Check your **Night mode** and brightness settings. If night mode is on and the night brightness is set very low (below 0.10), the display might look almost black. Try increasing the night brightness slider.
3. Make sure the device is powered and plugged in.

### I can't find the `TailWatch-XXXX` setup network

1. Make sure the device is powered on.
2. Check your phone's Wi-Fi list again — the network name appears there only when the device is in setup mode (i.e., when it can't join your home Wi-Fi).
3. Look at the device's screen. It should show `WIFI SETUP` and the network name. If it shows a flight card instead, the device is already connected to your home network, and you can visit the settings page instead.

### I forgot which Wi-Fi my device is on

1. Look at your router's device list (usually found in the router's admin page, often at `192.168.1.1`). Find "TailWatch" or "MatrixPortal" in the list — it will show the IP address.
2. Alternatively, plug the device into a USB cable connected to a computer and check the serial console output. The IP address is printed there.

### The settings page won't load

1. Make sure your phone is on the same Wi-Fi network as TailWatch.
2. Double-check the IP address. Check your router's device list for the address (it looks like `192.168.x.x`) -- it can change if your router reassigns it.
3. Wait 10–15 seconds and try again. TailWatch may be busy polling for aircraft data.

### Aircraft information is missing or incomplete

If the display shows partial data or says `NO LINK`, TailWatch is having trouble reaching the OpenSky aircraft data service. This is usually temporary. Wait a minute and the data should come back.

### I want to change my location without setting up Wi-Fi again

Simply visit the settings page on your home network and update the **Latitude**, **Longitude**, and **Box (miles each way)** fields. You don't need to rejoin Wi-Fi or restart.

---

## Tips for Best Results

- **Place it where you can see it**: The display is bright in daylight but dim at night. Mount it where it catches your eye during the day but won't be distracting at night.
- **Adjust your search radius**: A smaller box (5–10 miles) shows fewer planes but faster updates. A larger box shows more variety but longer waits between aircraft.
- **Experiment with filters**: If you're mostly interested in commercial airliners, hide helicopters and general aviation. If you want to see everything, disable the filters.
- **Check Wi-Fi signal**: Make sure your device has a good Wi-Fi signal. If it drops connection often, it may not update reliably.

Enjoy watching the skies!
