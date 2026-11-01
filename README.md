# Matrix · TF-C2 Websteuerung

Eine lokale Weboberfläche für ein **128 × 32 RGB-LED-Display mit TF-C2 V6**,
Firmware **0.5.9**, angeschlossen über einen USB-Seriell-Adapter an einen Raspberry Pi.
Version **1.2.0**. Die Anwendung läuft vollständig auf dem Raspberry; Windows und
PowerLED sind für den Betrieb nicht erforderlich.

## Funktionen

- Eigene Ansicht **Uhr & Datum**: Digital, gerahmte Tafel,
  analog + digital und zwei Weltzeitstädte. Drei Datumsformate,
  native laufende Sekunden, Zeitzonen und automatische Zeitabgleiche.
  Logos lassen sich links oder rechts neben der Uhrzeit einblenden. Das Datum
  wird exakt im gewählten Format gerendert und beim lokalen Tageswechsel erneuert.
  Binär- und Pac-Man-Ziffern sind auf dem getesteten Controller vorerst gesperrt;
  eingebettete Uhrschriften ergaben trotz Übertragungsbestätigung eine schwarze Anzeige.

- Texte, Umlaute, sieben Textfarben und farbige Hintergründe.
- Schriftgrößen 10–28 Pixel, auch unterschiedliche Größen pro Textzeile.
- Vertikale Zentrierung anhand der tatsächlich sichtbaren Buchstaben.
- Automatischer Umbruch und Platzprüfung, Standbild, Textseiten und Laufschrift.
- Feste native Übergangseffekte mit Vorschau der fertigen Pixelbilder.
- Logos hochladen, skalieren und allein oder neben Text anzeigen.
- LED-Rahmen: durchgehend, gestrichelt oder gepunktet, eigene Farbe und Stärke.
- Globale Hardwarehelligkeit in 16 Stufen mit Rücklesebestätigung.
- Szenenstudio mit Timeline, Drag-and-drop, Vorschaubildern, Undo/Redo und Projekten.
- RSS-/Atom-Quellen in der Webseite eintragen und automatisch aktualisieren.
- Dauerhafte Vorlagen, lokale SQLite-Datenbank und systemd-Autostart.

## Getestete Hardware

TF-C2 V6, Firmwarekennung `9121000509`, Controller-ID 1, 128 × 32 RGB,
CH340-USB-Adapter, 57600 Baud, 8N1. Dieses Panel verwendet die Farbplane-Reihenfolge
R/B/G. Der Encoder berücksichtigt diese Reihenfolge. Andere Controller, Firmware,
Auflösungen und Panelverdrahtungen sind nicht getestet und werden nicht als kompatibel
zugesichert. Die Verbindung prüft Kennung, ID und Auflösung vor dem Schreiben.

## Installation auf dem Raspberry Pi

Voraussetzung: aktuelles Raspberry Pi OS mit Python 3.11 oder neuer, Internetzugang
für die Installation und ein Benutzer mit sudo-Rechten. Getestet mit Python 3.13.

1. Das Release-Paket herunterladen und so entpacken, dass `~/tf-c2-web/server.py` existiert.
2. Den USB-Seriell-Adapter anschließen.
3. Im Terminal ausführen:

```sh
cd ~/tf-c2-web
bash install.sh
```

Falls der Installer die Gruppe `dialout` ergänzt, anschließend ab- und wieder
anmelden und den Raspberry neu starten. Den Gerätepfad bei Bedarf ermitteln:

```sh
ls -l /dev/serial/by-id/
nano ~/tf-c2-web/config.env
systemctl --user restart tf-c2-web
```

`TF_SERIAL_DEVICE` muss auf den Adapter zeigen. `TF_WEB_PORT` bestimmt den HTTP-Port.
Weitere lokale Hostnamen oder IP-Adressen lassen sich in `TF_ALLOWED_HOSTS` eintragen.
Browser öffnen: **http://IP-DES-RASPBERRY:8080/**.

Die Oberfläche verwendet kein Login und ist für das eigene vertrauenswürdige LAN
vorgesehen. Keine Router-Portfreigabe einrichten.

## Bedienung und Wartung

- [Bedienungsanleitung](docs/BEDIENUNG.md)
- [Uhr und Datum: Stile, Zeitquelle und Bedienung](UHR.md)
- [Betrieb, Sicherung und Fehlerbehebung](docs/BETRIEB.md)
- [Technik und Protokoll](docs/TECHNIK.md)
- [Versionshinweise](CHANGELOG.md)
- [Herkunft der Protokollreferenzen und Abhängigkeiten](NOTICE.md)

## Tests

```sh
cd ~/tf-c2-web
.venv/bin/python -m unittest -v test_control.py test_clocks.py
```

Die 51 Tests benötigen keinen angeschlossenen Controller. Sie prüfen unter anderem
Paketformat, Farbplanes, Textzentrierung, Rahmen, Hintergründe, Logos, Szenen und RSS.
Hardwaretests wurden zusätzlich am genannten Display durchgeführt.

GitHub Actions führt die Tests unter Linux aus. Private Inhalte gehören in `data/`
und sind von der Versionsverwaltung ausgeschlossen.
