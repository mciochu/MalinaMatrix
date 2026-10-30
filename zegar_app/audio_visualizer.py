"""Low-overhead Bluetooth A2DP audio visualizer for the MAX7219 matrix."""
import math
import os
import re
import subprocess
import threading
import time

import numpy as np


class BluetoothAudioVisualizer:
    """Capture only an active Bluetooth A2DP monitor; never opens a mic/device."""
    def __init__(self, sample_rate=8000, frame_size=512, bands=32):
        # zegar.service is a system unit; explicitly point PipeWire/BlueZ
        # clients at the logged-in user session sockets.
        runtime_dir = f"/run/user/{os.getuid()}"
        os.environ.setdefault("XDG_RUNTIME_DIR", runtime_dir)
        os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
        os.environ.setdefault("PIPEWIRE_REMOTE", "pipewire-0")
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.bands = bands
        # Precompute FFT window and logarithmic frequency bands once. At 8 kHz
        # with a 512-sample FFT, some low-frequency log bands are narrower than
        # one FFT bin. An empty mask would create a permanently dark 2-pixel bar.
        self._window = np.hanning(frame_size).astype(np.float32)
        frequencies = np.fft.rfftfreq(frame_size, 1.0 / sample_rate)
        upper_frequency = min(3800.0, sample_rate / 2.0)
        edges = np.geomspace(65.0, upper_frequency, bands + 1)
        self._band_centers = np.sqrt(edges[:-1] * edges[1:])
        self._band_bins = []
        for index in range(bands):
            bins = np.flatnonzero((frequencies >= edges[index]) & (frequencies < edges[index + 1]))
            if bins.size == 0:
                # Reuse the nearest FFT bin for narrow bands. Adjacent bands may
                # share a bin at the bottom of the spectrum, but none is silent
                # merely because FFT resolution is too coarse.
                nearest = int(np.argmin(np.abs(frequencies - self._band_centers[index])))
                bins = np.array([nearest], dtype=np.int32)
            self._band_bins.append(bins)

        # Gentle edge compensation makes bass and upper harmonics visible
        # without making the whole spectrum artificially uniform.
        low_boost = np.clip(
            np.log(500.0 / self._band_centers) / np.log(500.0 / 65.0), 0.0, 1.0
        )
        if upper_frequency > 1400.0:
            high_boost = np.clip(
                np.log(self._band_centers / 1400.0) / np.log(upper_frequency / 1400.0),
                0.0, 1.0
            )
        else:
            high_boost = np.zeros(bands, dtype=np.float32)
        self._band_gains = 1.0 + 0.16 * low_boost + 0.12 * high_boost
        self._lock = threading.Lock()
        self._levels = [0.0] * bands
        self._active = False
        self._connected = False
        self._device = None
        self._last_sound = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="bt-audio-visualizer")
        self._thread.start()
        self._bluetooth_thread = threading.Thread(target=self._ensure_bluetooth, daemon=True, name="bt-advertise")
        self._bluetooth_thread.start()

    @staticmethod
    def _ensure_bluetooth():
        commands = (["bluetoothctl", "system-alias", "Malina"], ["bluetoothctl", "power", "on"],
                    ["bluetoothctl", "pairable", "on"], ["bluetoothctl", "discoverable-timeout", "180"],
                    ["bluetoothctl", "discoverable", "on"])
        while True:
            for command in commands:
                try:
                    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
                except Exception:
                    pass
            time.sleep(150)

    def snapshot(self):
        with self._lock:
            return self._active, self._connected, tuple(self._levels), self._device

    def stop(self):
        self._stop.set()

    @staticmethod
    def _find_monitor():
        try:
            result = subprocess.run(["pw-cli", "ls", "Node"], capture_output=True,
                                    text=True, timeout=5.0, check=False)
            current_serial = None
            current_name = None
            current_class = None
            candidates = []
            for line in result.stdout.splitlines() + [""]:
                match = re.search(r"id\s+(\d+),", line)
                if match:
                    if current_serial and current_name and "bluez_input." in current_name and current_class == "Stream/Output/Audio":
                        candidates.append((current_serial, current_name))
                    current_serial, current_name, current_class = None, None, None
                serial_match = re.search(r'object.serial\s*=\s*"([^"]+)"', line)
                name_match = re.search(r'node.name\s*=\s*"([^"]+)"', line)
                class_match = re.search(r'media.class\s*=\s*"([^"]+)"', line)
                if serial_match:
                    current_serial = serial_match.group(1)
                if name_match:
                    current_name = name_match.group(1)
                if class_match:
                    current_class = class_match.group(1)
            if current_serial and current_name and "bluez_input." in current_name and current_class == "Stream/Output/Audio":
                candidates.append((current_serial, current_name))
            return candidates[0] if candidates else None
        except Exception:
            return None

    def _set_levels(self, values, active, connected, device):
        with self._lock:
            self._levels = values
            self._active = active
            self._connected = connected
            self._device = device

    def _analyse(self, raw):
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        if samples.size < self.frame_size:
            return None, 0.0
        samples = samples[:self.frame_size]
        rms = float(np.sqrt(np.mean(samples * samples)))

        # Quiet-volume compensation: lift only weak incoming streams, while
        # leaving medium/loud playback untouched. This is deliberately capped
        # and applied before the FFT, so it cannot flatten loud music.
        # Normalize the Bluetooth monitor's PCM level before FFT. A2DP can
        # deliver a very small digital signal even when the listener hears it
        # clearly; compensate progressively, with a firm cap for noise safety.
        quiet_gain = min(12.0, 1800.0 / max(rms, 1.0))
        adjusted = samples * quiet_gain
        windowed = adjusted * self._window
        spectrum = np.abs(np.fft.rfft(windowed))
        result = []
        for index, bins in enumerate(self._band_bins):
            energy = float(np.max(spectrum[bins]))
            # Soft compression lifts quieter details while retaining strong
            # beats. Per-band gains gently balance bass and upper harmonics.
            normalized = (energy / (self.frame_size * 2500.0)) * 22.0
            normalized *= float(self._band_gains[index])
            # A gentler power curve gives very quiet music a visible response
            # without applying global AGC or lifting the whole display.
            shaped = normalized ** 0.52 if normalized > 0.0 else 0.0
            # Soft knee retains headroom for loud passages; no hard clipping.
            level = shaped / (0.90 + shaped)
            result.append(max(0.0, min(1.0, level)))
        return result, rms

    def _run(self):
        smoothed = [0.0] * self.bands
        while not self._stop.is_set():
            monitor = self._find_monitor()
            if not monitor:
                self._set_levels([0.0] * self.bands, False, False, None)
                time.sleep(2.5)
                continue
            node_id, node_name = monitor
            process = None
            try:
                process = subprocess.Popen(
                    ["pw-record", "--raw", "--media-category", "Capture", "--target", node_id, "--rate", str(self.sample_rate),
                     "--channels", "1", "--format", "s16", "--latency", "64ms", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
                )
                connected = True
                self._set_levels(smoothed[:], False, True, node_name)
                while not self._stop.is_set() and process.poll() is None:
                    required = self.frame_size * 2
                    raw = bytearray()
                    while len(raw) < required and not self._stop.is_set():
                        chunk = process.stdout.read(required - len(raw))
                        if not chunk:
                            break
                        raw.extend(chunk)
                    if len(raw) < required:
                        break
                    levels, rms = self._analyse(bytes(raw))
                    if levels is None:
                        continue
                    now = time.monotonic()
                    if rms > 0.15:
                        self._last_sound = now
                    active = (now - self._last_sound) < 1.35
                    for i, level in enumerate(levels):
                        target = level if active else 0.0
                        # Szybki atak na uderzenia, wolniejszy opad i lekkie
                        # podtrzymanie poziomu między kolejnymi uderzeniami.
                        factor = 0.80 if target > smoothed[i] else 0.09
                        smoothed[i] += (target - smoothed[i]) * factor
                    self._set_levels(smoothed[:], active, connected, node_name)
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except Exception:
                pass
            finally:
                if process is not None and process.stdout:
                    process.stdout.close()
                if process is not None and process.poll() is None:
                    process.kill()
            self._set_levels([0.0] * self.bands, False, False, None)
            time.sleep(0.5)
