# NINA_MC - BBK Warnbot fuer MeshCore

NINA_MC fragt die oeffentliche BBK/NINA-Warn-API ab und verteilt neue amtliche
Warnmeldungen ueber ein MeshCore LoRa-Funknetz. Der Bot ist fuer den Betrieb auf
einem Raspberry Pi mit angeschlossenem MeshCore Companion gedacht.

## Funktionen

- Pollt die BBK/NINA-API in regelmaessigen Intervallen
- Sendet neue Warnmeldungen in einen konfigurierten MeshCore-Kanal
- Erkennt Entwarnungen auch dann, wenn sie nur im Titel markiert sind
- Verhindert Doppelmeldungen fuer bereits bekannte Warn-IDs
- Sendet einen taeglichen Heartbeat
- Meldet API- oder Versandfehler optional in einen MeshCore-Room

## Nachrichtenformat

```text
[nina gf] alert/severe: hochwasser aller - pegel kritisch
[nina wob] update/minor: trinkwasserwarnung wolfsburg-nord...
[nina bs] entwarnung: gasaustritt braunschweig-suedstadt
[nina] heartbeat: keine aktiven warnungen (gf, wob, bs, gs, pe)
```

Die Nachrichten werden vor dem Versand in Kleinbuchstaben umgewandelt, weil der
verwendete Companion nur Kleinbuchstaben unterstuetzt.

## Channel-Routing

Waehrend der Migration werden Warnungen parallel in mehrere offene MeshCore-
Channels gesendet:

| Slot | Channel       | Zweck |
|------|---------------|-------|
| 2    | #38ninawarn   | Neuer Sammelchannel fuer alle Warnungen |
| 3    | #wobninawarn  | Warnungen fuer Wolfsburg |
| 4    | #bsninawarn   | Warnungen fuer Braunschweig |
| 5    | #gsninawarn   | Warnungen fuer Goslar |
| 6    | #peninawarn   | Warnungen fuer Peine |
| 7    | #gfninawarn   | Legacy-Sammelchannel und Warnungen fuer Gifhorn |

Eine Peine-Warnung wird zum Beispiel an Slot 7, Slot 2 und Slot 6 gesendet.
Eine Gifhorn-Warnung wird an Slot 7 und Slot 2 gesendet, ohne Slot 7 doppelt
zu nutzen. Alle Sendungen verwenden den Scope `#de-mitte`.

## Ueberwachte Regionen

Die Standardkonfiguration ueberwacht fuenf Regionen in Niedersachsen:

| Kuerzel | Region             | AGS          |
|---------|--------------------|--------------|
| gf      | Landkreis Gifhorn  | 031510000000 |
| wob     | Stadt Wolfsburg    | 031030000000 |
| bs      | Stadt Braunschweig | 031010000000 |
| gs      | Landkreis Goslar   | 031530000000 |
| pe      | Landkreis Peine    | 031570000000 |

Andere Regionen koennen in `AGS_LIST` in `nina_mc.py` eingetragen werden. Die
BBK/NINA-API erwartet AGS-Codes auf Kreisebene.

## Voraussetzungen

- Raspberry Pi oder anderer Linux-Host mit Python 3
- MeshCore Companion per USB
- `meshcore-cli`, z.B. via `pipx`
- Python-Abhaengigkeiten aus `requirements.txt`

```bash
python3 -m pip install -r requirements.txt
pipx install meshcore-cli
```

## Konfiguration

Die wichtigsten Parameter stehen am Anfang von `nina_mc.py` und koennen per
Umgebungsvariable ueberschrieben werden:

| Variable | Environment | Bedeutung |
|----------|-------------|-----------|
| `AGS_LIST` | - | Zu ueberwachende Regionen und AGS-Codes |
| `LEGACY_CHANNEL` | `NINA_MC_LEGACY_CHANNEL` / `NINA_MC_CHANNEL` | Bisheriger Sammelchannel |
| `GLOBAL_CHANNEL` | `NINA_MC_GLOBAL_CHANNEL` | Neuer Sammelchannel |
| `REGION_CHANNELS` | - | Regionale MeshCore-Channelnummern |
| `SCOPE` | `NINA_MC_SCOPE` | MeshCore Flood-Scope |
| `POLL_INTERVAL` | `NINA_MC_POLL_INTERVAL` | Abfrageintervall in Sekunden |
| `HEARTBEAT_INTERVAL` | `NINA_MC_HEARTBEAT_INTERVAL` | Heartbeat-Intervall in Sekunden |
| `MESHCORE` | `NINA_MC_MESHCORE` | Pfad zu `meshcore-cli` |
| `SERIAL` | `NINA_MC_SERIAL` | USB-Schnittstelle des Companions |
| `BAUD` | `NINA_MC_BAUD` | Baudrate |
| `MAX_TITLE` | `NINA_MC_MAX_TITLE` | Maximale Titellaenge |
| `ROOM` | `NINA_MC_ROOM` | Optionaler MeshCore-Room fuer Fehlermeldungen |
| `LOG_FILE` | `NINA_MC_LOG_FILE` | Logdatei |

Vor dem Einsatz sollten mindestens `NINA_MC_MESHCORE`, `NINA_MC_SERIAL`,
`NINA_MC_LEGACY_CHANNEL`, `NINA_MC_GLOBAL_CHANNEL`, `NINA_MC_SCOPE`,
`NINA_MC_ROOM` und `NINA_MC_LOG_FILE` an die
eigene MeshCore-Installation angepasst werden.

## Deployment

Script auf den Zielhost kopieren:

```bash
scp nina_mc.py user@raspberrypi:/home/user/nina_mc.py
```

Die systemd-Unit `nina_mc.service` verwendet beispielhafte Pfade. Vor dem
Installieren sollten `ExecStart`, `WorkingDirectory` und `User` angepasst werden.

```bash
sudo cp nina_mc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable nina_mc
sudo systemctl start nina_mc
```

## Betrieb

```bash
sudo systemctl status nina_mc
sudo systemctl restart nina_mc
sudo journalctl -u nina_mc -f
tail -f /home/user/nina_mc.log
```

## Tests

Die Unit-Tests laufen lokal ohne Raspberry Pi und ohne Companion. Externe
Aufrufe werden gemockt.

```bash
python3 -m unittest test_nina_mc -v
```

Aktuell decken 25 Tests ab:

- Titelkuerzung und Prefix-Bereinigung
- Nachrichtenformatierung fuer Alert, Update und Entwarnung
- Channel-Routing fuer Legacy-, Sammel- und Regionalchannels
- API-Fehlerbehandlung
- Verhinderung von Doppelmeldungen

## API

Genutzt wird die oeffentliche BBK/NINA-API:

```text
https://warnung.bund.de/api31/dashboard/{AGS}.json
```

Es ist keine Authentifizierung erforderlich. Die Daten sind auf Kreisebene
aggregiert.
