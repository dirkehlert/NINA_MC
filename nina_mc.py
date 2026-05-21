"""
nina_mc.py - BBK NINA Warnbot fuer MeshCore
============================================
Fragt alle 5 Minuten die BBK NINA Warn-API ab und sendet neue Warnmeldungen
in einen MeshCore-Kanal via angeschlossenem Companion.

Ueberwachte Regionen: Gifhorn (GF), Wolfsburg (WOB), Braunschweig (BS), Peine (PE)
Systemd-Dienst: /etc/systemd/system/nina_mc.service
"""

import os
import subprocess
import requests
import re
import time
import logging
from datetime import datetime, timedelta

# AGS = Amtlicher Gemeindeschluessel (12-stellig, Kreisebene)
# Format: https://warnung.bund.de/api31/dashboard/{AGS}.json
AGS_LIST = {
    "031510000000": "gf",   # Landkreis Gifhorn
    "031030000000": "wob",  # Stadt Wolfsburg
    "031010000000": "bs",   # Stadt Braunschweig
    "031570000000": "pe",   # Landkreis Peine
}

NINA_BASE = "https://warnung.bund.de/api31/dashboard/{}.json"

CHANNEL = int(os.getenv("NINA_MC_CHANNEL", "7"))
SCOPE = os.getenv("NINA_MC_SCOPE", "#de-mitte")
POLL_INTERVAL = int(os.getenv("NINA_MC_POLL_INTERVAL", "300"))
HEARTBEAT_INTERVAL = int(os.getenv("NINA_MC_HEARTBEAT_INTERVAL", "86400"))

# meshcore-cli Verbindungsparameter
MESHCORE = os.getenv("NINA_MC_MESHCORE", "meshcore-cli")
SERIAL = os.getenv("NINA_MC_SERIAL", "/dev/ttyACM0")
BAUD = os.getenv("NINA_MC_BAUD", "115200")

MAX_TITLE = int(os.getenv("NINA_MC_MAX_TITLE", "60"))
ROOM = os.getenv("NINA_MC_ROOM", "NINA Alerts")
LOG_FILE = os.getenv("NINA_MC_LOG_FILE", "nina_mc.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def send_mesh(text):
    """Sendet eine Nachricht in den Warnkanal (Kanal 7, scope #de-mitte)."""
    text = text.lower()  # Companion unterstuetzt nur Kleinbuchstaben
    try:
        result = subprocess.run(
            [MESHCORE, "-s", SERIAL, "-b", BAUD, "-q",
             "scope", SCOPE, "chan", str(CHANNEL), text],
            capture_output=True, text=True
        )
    except OSError as e:
        logging.error(f"meshcore-cli fehler: {e}")
        return
    if result.returncode != 0:
        logging.error(f"meshcore-cli fehler: {result.stderr}")
    else:
        logging.info(f"gesendet: {text}")

def send_room(text):
    """Sendet eine Direktnachricht an den MeshCore Room (nur fuer Fehler)."""
    text = text.lower()
    try:
        result = subprocess.run(
            [MESHCORE, "-s", SERIAL, "-b", BAUD, "-q",
             "msg", ROOM, text],
            capture_output=True, text=True
        )
    except OSError as e:
        logging.error(f"room fehler: {e}")
        return
    if result.returncode != 0:
        logging.error(f"room fehler: {result.stderr}")
    else:
        logging.info(f"room: {text}")

def shorten_title(title):
    """Kuerzt den BBK-Titel fuer die Uebertragung per Funk.
    Entfernt redundante Praeifxe wie '3. Aktualisierung! - '.
    'Entwarnung:' wird NICHT entfernt — format_warning prueft darauf.
    """
    title = re.sub(r"^\d+\.\s*Aktualisierung!?\s*-\s*", "", title)
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rsplit(" ", 1)[0] + "..."
    return title

def format_warning(w, prefix):
    """Formatiert eine BBK-Warnung als kurze Funknachricht.
    Beispiel: '[nina gf] alert/severe: hochwasser aller - pegel...'

    Entwarnung wird erkannt wenn:
    - type == 'cancel', ODER
    - Titel beginnt mit 'Entwarnung:' (BBK sendet nicht immer type=cancel)
    """
    raw_title = w.get("i18nTitle", {}).get("de", "unbekannte warnung")
    severity = w.get("severity", "").lower()  # minor / moderate / severe / extreme
    wtype = w.get("type", "").lower()         # alert / update / cancel

    # Entwarnung erkennen — auch wenn type nicht explizit 'cancel' ist
    is_cancel = wtype == "cancel" or raw_title.lower().startswith("entwarnung")

    # "Entwarnung: " Prefix aus Titel entfernen, da wir es selbst voranstellen
    clean_title = re.sub(r"^Entwarnung:\s*", "", raw_title)
    title = shorten_title(clean_title)

    if is_cancel:
        return f"[nina {prefix}] entwarnung: {title}"
    if wtype and severity:
        return f"[nina {prefix}] {wtype}/{severity}: {title}"
    # Fallback falls type oder severity leer (kommt gelegentlich vor)
    return f"[nina {prefix}] warnung: {title}"

def fetch_warnings(ags, prefix):
    """Fragt die BBK NINA API fuer einen Landkreis/Stadt ab.
    Gibt eine Liste von Warnungen zurueck, oder None bei Fehler.
    """
    try:
        r = requests.get(NINA_BASE.format(ags), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"api fehler {prefix}: {e}")
        send_room(f"[nina {prefix}] fehler: nina api nicht erreichbar")
        return None

def main():
    logging.info("nina-mc bot gestartet")
    regions = ", ".join(AGS_LIST.values())
    send_mesh(f"[nina] bot gestartet - bbk warnungen {regions}")

    # Bereits gemeldete Warnungs-IDs pro Region (verhindert Doppelmeldungen)
    seen_ids = {ags: set() for ags in AGS_LIST}
    # Erster Heartbeat nach 1 Stunde (nicht erst nach 24h)
    last_heartbeat = datetime.now() - timedelta(hours=23)

    while True:
        now = datetime.now()
        total = 0

        for ags, prefix in AGS_LIST.items():
            warnings = fetch_warnings(ags, prefix)
            if warnings is not None:
                current_ids = {w["id"] for w in warnings}

                # Neue Warnungen senden
                for w in warnings:
                    if w["id"] not in seen_ids[ags]:
                        send_mesh(format_warning(w, prefix))

                # Aufgehobene Warnungen nur loggen (keine Funkmeldung)
                for wid in seen_ids[ags] - current_ids:
                    logging.info(f"warnung aufgehoben [{prefix}]: {wid}")

                seen_ids[ags] = current_ids
                total += len(current_ids)
                logging.info(f"poll ok [{prefix}]: {len(current_ids)} aktive warnung(en)")

        # Taeglicher Heartbeat im Kanal
        if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL:
            regions = ", ".join(AGS_LIST.values())
            if total == 0:
                send_mesh(f"[nina] heartbeat: keine aktiven warnungen ({regions})")
            else:
                send_mesh(f"[nina] heartbeat: {total} aktive warnung(en) ({regions})")
            last_heartbeat = now

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
