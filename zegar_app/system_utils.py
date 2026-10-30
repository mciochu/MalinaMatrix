"""System time synchronization and optional startup-wait helpers."""
import subprocess
import sys
import time

from luma.core.render import canvas
from luma.core.legacy import text

def is_time_synced():
    # 1. Sprawdzenie przez timedatectl
    try:
        res = subprocess.run(["timedatectl", "show", "--property=NTPSynchronized"], 
                             capture_output=True, text=True, timeout=2)
        if "NTPSynchronized=yes" in res.stdout:
            return True
    except Exception:
        pass
    
    # 2. Sprawdzenie przez ntpstat (jeśli dostępny)
    try:
        res = subprocess.run(["ntpstat"], capture_output=True, timeout=2)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 3. Fallback: Jeśli rok systemowy > 2024, uznajemy że czas został ustawiony (np. przez RTC lub wcześniejszą synchronizację)
    try:
        if time.localtime().tm_year > 2024:
            return True
    except Exception:
        pass
        
    return False

def force_time_sync():
    try:
        # Próba wymuszenia synchronizacji
        subprocess.run(["sudo", "systemctl", "restart", "systemd-timesyncd"], timeout=5)
    except Exception:
        pass

def wait_for_time_sync(device, font, verbose=True, min_duration=2.0):
    if verbose:
        print("Rozpoczynanie synchronizacji czasu...", file=sys.stderr)
    
    force_time_sync()
    
    frame = 0
    start_time = time.time()
    timeout = 30  # Czekaj maksymalnie 30 sekund
    
    # Mała animacja kółeczka 3x3
    # Klatki animacji (relatywne współrzędne x,y od sp_x, sp_y)
    spinner_frames = [
        [(1,0)], [(2,0)], [(2,1)], [(2,2)], [(1,2)], [(0,2)], [(0,1)], [(0,0)]
    ]
    
    while True:
        elapsed = time.time() - start_time
        
        # Sprawdzamy synchronizację dopiero po upływie minimalnego czasu (np. 2 sekundy),
        # aby animacja była widoczna na ekranie przy uruchomieniu.
        if elapsed >= min_duration:
            if is_time_synced():
                if verbose:
                    print("Czas został pomyślnie zsynchronizowany.", file=sys.stderr)
                return True
            if elapsed >= timeout:
                break
        
        with canvas(device) as draw:
            # Napis "Czekaj" na środku/lewo
            text(draw, (4, 1), "Czekaj", font=font, fill="white")
            
            # Animacja "kółeczka" po prawej (dopasowana do szerokości wyświetlacza)
            sp_x = device.width - 10
            sp_y = 2
            # Rysuj kropkę na podstawie klatki
            for dx, dy in spinner_frames[frame % len(spinner_frames)]:
                draw.point((sp_x + dx, sp_y + dy), fill="white")
                
        frame += 1
        time.sleep(0.15)
        
    if verbose:
        print("Przekroczono limit czasu synchronizacji.", file=sys.stderr)
    return False
