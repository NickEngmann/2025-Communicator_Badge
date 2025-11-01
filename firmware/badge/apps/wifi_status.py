"""
WiFi Status App for Hackaday Supercon 2025 Communicator Badge
Displays WiFi connection status with LVGL UI
"""

import uasyncio as aio  # type: ignore
from apps.base_app import BaseApp
from ui.page import Page
import lvgl


class WiFiStatusPage(Page):
    """LVGL page for WiFi status display"""

    def __init__(self, wifi_manager):
        super().__init__()
        self.wifi_manager = wifi_manager

        # Create UI layout
        self.create_infobar([
            "WiFi Status",
            f"SSID: {wifi_manager.ssid}",
        ])

        self.create_content()
        self.create_menubar(("", "", "", "", "Home"))

        # Status display labels
        self.status_label = lvgl.label(self.content)
        self.status_label.set_text("Initializing...")
        self.status_label.set_style_text_font(lvgl.font_montserrat_16, 0)
        self.status_label.align(lvgl.ALIGN.TOP_LEFT, 10, 10)

        self.ip_label = lvgl.label(self.content)
        self.ip_label.set_text("IP: Not connected")
        self.ip_label.align(lvgl.ALIGN.TOP_LEFT, 10, 40)

        self.ping_label = lvgl.label(self.content)
        self.ping_label.set_text("Ping: -")
        self.ping_label.align(lvgl.ALIGN.TOP_LEFT, 10, 70)

        self.stats_label = lvgl.label(self.content)
        self.stats_label.set_text("Statistics: -")
        self.stats_label.align(lvgl.ALIGN.TOP_LEFT, 10, 100)

    def update_display(self):
        """Update all status information on display"""
        info = self.wifi_manager.get_info()

        # Status with color
        status_text = f"Status: {info['status_string']}"
        self.status_label.set_text(status_text)

        # IP address
        if info['ip']:
            self.ip_label.set_text(f"IP: {info['ip']}")
        else:
            self.ip_label.set_text("IP: Not connected")

        # Ping status
        if info['ping_count'] > 0:
            ping_status = "OK" if info['last_ping_ok'] else "FAIL"
            self.ping_label.set_text(f"Last Ping: {ping_status}")
        else:
            self.ping_label.set_text("Ping: Waiting...")

        # Statistics
        if info['ping_count'] > 0:
            success_rate = ((info['ping_count'] - info['ping_failures']) /
                           info['ping_count'] * 100)
            stats_text = f"Pings: {info['ping_count']} ({success_rate:.1f}% success)"
            self.stats_label.set_text(stats_text)
        else:
            self.stats_label.set_text("Statistics: No data yet")


class WiFiStatusApp(BaseApp):
    """
    WiFi Status Application
    Runs in background, updates WiFi status display
    """

    def __init__(self, name: str, badge, wifi_manager):
        super().__init__(name, badge)
        self.wifi_manager = wifi_manager
        self.page = None

        # Set update intervals
        self.foreground_sleep_ms = 500  # Update UI every 500ms when visible
        self.background_sleep_ms = 2000  # Update every 2s in background

        # Register status callback
        self.wifi_manager.add_status_callback(self.on_wifi_status_change)

    def start(self):
        """Start the WiFi status app"""
        super().start()

    def on_wifi_status_change(self, wifi_manager):
        """Called when WiFi status changes"""
        # Update page if it exists
        if self.page:
            self.page.update_display()

    def switch_to_foreground(self):
        """Setup and display the WiFi status page"""
        super().switch_to_foreground()

        # Create page if it doesn't exist
        if not self.page:
            self.page = WiFiStatusPage(self.wifi_manager)

        # Update and display the screen
        self.page.update_display()
        self.page.replace_screen()

    def switch_to_background(self):
        """Return to background mode"""
        # Clean up the page to free memory
        self.page = None
        super().switch_to_background()

    def run_foreground(self):
        """Update display while in foreground"""
        if self.page:
            self.page.update_display()

        # Handle keyboard input - F5 to go home
        if self.badge.keyboard.f5():
            self.badge.display.clear()
            self.switch_to_background()

    def run_background(self):
        """Background tasks - just monitor status changes"""
        # Status updates happen via callbacks
        pass

    def get_status_icon(self):
        """
        Get a status icon/text for display in other apps' infobars
        Can be called by other apps to show WiFi status
        """
        info = self.wifi_manager.get_info()

        if info['connected']:
            if info['last_ping_ok']:
                return "WiFi:OK"
            else:
                return "WiFi:!"
        else:
            return "WiFi:X"
