import micropython
import time
import asyncio as aio  # type: ignore

try:
    from hardware.badge import Badge
    from net.net import badgenet, capture_all_packets

    ## Import your app here
    from apps import app_menu, chat, config_manager, usb_debug, nametag, talks
    from apps import wifi_status, userB, userC, userD  ## An invitation (userA replaced by wifi_status)


except Exception as ex:
    # If anything goes wrong at import time, wait a second and print it
    # Sometimes these are hard to see, so the delay and extra print may help
    import sys
    import time

    time.sleep(1)
    sys.print_exception(ex)
    raise


async def main():
    print("Initializing main...")
    badge = Badge()
    badgenet.init(badge)

    # Start WiFi connection in background (non-blocking)
    async def start_wifi():
        """Start WiFi connection with timeout, then begin monitoring"""
        print("WiFi: Starting connection attempt...")
        connected = await badge.wifi.connect()
        if connected:
            print("WiFi: Starting monitoring loop...")
            await badge.wifi.monitor_loop()
        else:
            print("WiFi: Skipping - continuing without WiFi")

    # Create WiFi task (runs in background, won't block boot)
    wifi_task = aio.create_task(start_wifi())

    # Create WiFi status app
    wifi_app = wifi_status.WiFiStatusApp("WiFi", badge, badge.wifi)

    # Link them into the menu system here, for starters
    user_apps = [
        wifi_app,  # WiFi status replaces User A
        userB.App("User B", badge),
        userC.App("User C", badge),
        userD.App("User D", badge),
        # Only 4, the 5th button goes to Home
    ]
    user_menu = app_menu.AppMenu("User", badge, user_apps, False)
    # These apps are on the main screen when the badge boots
    primary_apps = [
        chat.ChatApp("Chat", badge),
        talks.Talks("Talks", badge),
        nametag.App("Nametag", badge),
        user_menu,
        config_manager.ConfigManager("Config", badge),
    ]
    # These apps aren't listed in the menus, so put them here to get started below
    backgrounded_apps = [
        usb_debug.UsbDebug("USB Debug", badge),
    ]
    main_menu = app_menu.AppMenu("Main", badge, primary_apps, True)
    for app in primary_apps:
        if app:
            app.start()
    for app in user_apps:
        if app:
            app.start()
    for app in backgrounded_apps:
        app.start()
    main_menu.start()
    user_menu.start()
    main_menu.switch_to_foreground()

    # To capture all network packets for debugging, set to True
    capture_all_packets(False)
    print("Badge is up and running!")
    print("If you want the Python REPL, try one Ctrl-C or one Ctrl-D")

    while True:
        await aio.sleep(60)
        print("Main 60s heartbeat --^v--^v--")
        micropython.mem_info()


if __name__ == "__main__":
    aio.run(main())
