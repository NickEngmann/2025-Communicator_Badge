"""
WiFi Manager for Hackaday Supercon 2025 Communicator Badge
Handles non-blocking WiFi connection with timeout and periodic pinging
"""

import uasyncio as aio  # type: ignore
import network
import time


class WiFiStatus:
    """WiFi connection status states"""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    FAILED = 3
    PINGING = 4


class WiFiManager:
    """
    Manages WiFi connection with non-blocking operation and periodic health checks
    """

    def __init__(self, ssid="NYCR24", password="clubmate",
                 connect_timeout_s=120, ping_interval_s=15):
        """
        Initialize WiFi manager

        Args:
            ssid: WiFi network SSID
            password: WiFi password
            connect_timeout_s: Maximum time to wait for connection (default: 120s)
            ping_interval_s: Interval between ping checks (default: 15s)
        """
        self.ssid = ssid
        self.password = password
        self.connect_timeout_s = connect_timeout_s
        self.ping_interval_s = ping_interval_s

        self.wlan = None
        self.status = WiFiStatus.DISCONNECTED
        self.ip_address = None
        self.last_ping_success = False
        self.ping_count = 0
        self.ping_failures = 0

        # Status callback for UI updates
        self.status_callbacks = []

    def add_status_callback(self, callback):
        """Add callback function to be called on status changes"""
        self.status_callbacks.append(callback)

    def _notify_status_change(self):
        """Notify all registered callbacks of status change"""
        for callback in self.status_callbacks:
            try:
                callback(self)
            except Exception as e:
                print(f"WiFi status callback error: {e}")

    async def connect(self):
        """
        Attempt to connect to WiFi with timeout
        Returns True if connected, False if timed out
        Non-blocking - uses asyncio
        """
        print(f"WiFi: Connecting to {self.ssid}...")
        self.status = WiFiStatus.CONNECTING
        self._notify_status_change()

        # Initialize WiFi interface
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)

        # Start connection attempt
        self.wlan.connect(self.ssid, self.password)

        # Wait for connection with timeout
        start_time = time.time()
        while not self.wlan.isconnected():
            if time.time() - start_time > self.connect_timeout_s:
                print(f"WiFi: Connection timeout after {self.connect_timeout_s}s")
                self.status = WiFiStatus.FAILED
                self._notify_status_change()
                return False

            # Yield to event loop every 500ms
            await aio.sleep_ms(500)

        # Connected successfully
        self.ip_address = self.wlan.ifconfig()[0]
        self.status = WiFiStatus.CONNECTED
        print(f"WiFi: Connected! IP: {self.ip_address}")
        self._notify_status_change()

        # Do initial ping test
        await self.ping_check()

        return True

    async def ping_check(self):
        """
        Perform a ping check to verify connectivity
        Uses simple socket connection as MicroPython doesn't have ICMP ping
        """
        import socket

        self.status = WiFiStatus.PINGING
        self._notify_status_change()

        self.ping_count += 1

        try:
            # Try to resolve and connect to a common DNS server
            # This is a lightweight connectivity check
            addr_info = socket.getaddrinfo("8.8.8.8", 53)
            addr = addr_info[0][-1]

            s = socket.socket()
            s.settimeout(2)  # Shorter timeout to avoid blocking

            # Try to connect - MicroPython doesn't have connect_ex
            try:
                s.connect(addr)
                s.close()
                self.last_ping_success = True
                print(f"WiFi: Ping #{self.ping_count} successful")
            except OSError as e:
                s.close()
                self.last_ping_success = False
                self.ping_failures += 1
                print(f"WiFi: Ping #{self.ping_count} failed: {e}")

        except Exception as e:
            self.last_ping_success = False
            self.ping_failures += 1
            print(f"WiFi: Ping #{self.ping_count} error: {e}")

        # Return to connected status
        self.status = WiFiStatus.CONNECTED
        self._notify_status_change()

        # Yield to event loop after ping
        await aio.sleep_ms(10)

        return self.last_ping_success

    async def monitor_loop(self):
        """
        Main monitoring loop - runs continuously in background
        Performs periodic ping checks and monitors connection
        """
        while True:
            if self.wlan and self.wlan.isconnected():
                # Perform periodic ping check
                await self.ping_check()
                await aio.sleep(self.ping_interval_s)
            else:
                # If disconnected, update status
                if self.status == WiFiStatus.CONNECTED:
                    print("WiFi: Connection lost")
                    self.status = WiFiStatus.DISCONNECTED
                    self.ip_address = None
                    self._notify_status_change()

                # Wait before checking again
                await aio.sleep(5)

    def get_status_string(self):
        """Get human-readable status string"""
        if self.status == WiFiStatus.DISCONNECTED:
            return "Disconnected"
        elif self.status == WiFiStatus.CONNECTING:
            return "Connecting..."
        elif self.status == WiFiStatus.CONNECTED:
            ping_status = "OK" if self.last_ping_success else "FAIL"
            return f"Connected ({ping_status})"
        elif self.status == WiFiStatus.FAILED:
            return "Failed"
        elif self.status == WiFiStatus.PINGING:
            return "Pinging..."
        return "Unknown"

    def get_info(self):
        """Get WiFi connection information"""
        return {
            'status': self.status,
            'status_string': self.get_status_string(),
            'ssid': self.ssid,
            'ip': self.ip_address,
            'connected': self.wlan and self.wlan.isconnected(),
            'ping_count': self.ping_count,
            'ping_failures': self.ping_failures,
            'last_ping_ok': self.last_ping_success,
        }
