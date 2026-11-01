# Matrix · TF-C2-Web

Lokale Websteuerung für den TF-C2 V6 an `raspberrypi`, Display 128×32, Firmware 0.5.9,
Controller-ID 1, USB-CH340 an 57600 Baud / 8N1.

Aufruf: http://raspberrypi:8080/ oder http://IP-DES-RASPBERRY:8080/

## Funktionen

- Eigene Texte, Umlaute, Schriftgrößen, Farbe und Ausrichtung.
- Schriftgrößen 10, 11, 12, 14, 16, 20, 24 und 28 px. Optional getrennte Größen:
  erste mit Enter getrennte Textzeile in der ersten Größe, zweite und weitere in
  der zweiten Größe. Umbrüche behalten die Größe ihrer ursprünglichen Textzeile.
  Die Platzprüfung summiert die tatsächlichen Zeilenhöhen. Unterschiedliche Größen
  verwenden Standbild oder Textseiten; die Gestaltung wird mit Vorlagen gespeichert.
- Automatischer Textumbruch auf lesbare Seiten oder fortlaufende Laufschrift.
- Vorschau aus denselben Rasterdaten, die das Display erhält.
- Textvorlagen mit gespeicherter Gestaltung.
- Szenenstudio mit Timeline, Drag-and-drop (zusätzlich Pfeile für Tastatur/Touch),
  Miniaturvorschau je Szene, Ablaufvorschau, Bearbeiten, Duplizieren und Rückgängig/Wiederholen.
  Projekte werden auf dem Raspberry gespeichert; der aktuelle Entwurf zusätzlich im Browser.
  Eine Folge enthält bis zu 30 Szenen und insgesamt 120 Seiten. Szenen dürfen Text,
  unterschiedliche Schriftgrößen, Logos und jeweils einen festen Übergang enthalten.
  Die gesamte Folge wird als ein natives Programm mit verketteten Seiten übertragen.
  Die Zeitachse stellt Vorschau-/Standzeiten dar; native Übergänge und Laufschrift
  können die tatsächliche Laufzeit verlängern. Sie ist keine bildgenaue Video-Zeitachse.
- Logo-Upload (PNG, JPG, WebP, BMP, bis 2 MB und 4 Megapixel), dauerhafte Bildauswahl
  und Vorlagen mit Logo. Transparenz und Seitenverhältnis bleiben erhalten.
- Logo allein oder links/rechts neben Text; maximale Breite, Originalfarben,
  Farbumkehr oder einfarbige Darstellung für transparente Motive.
  Textumbruch und Pixelprüfung berücksichtigen den tatsächlich verbleibenden Platz.
  Logo + Text verwendet Standbild oder Textseiten, damit das Logo nicht mitscrollt.
- Automatische Pixelprüfung für jede Schriftgröße. Standbild ist nur auswählbar,
  wenn der gesamte Text nach Umbruch auf eine Seite passt. Unpassende Schriftgrößen
  werden für Standbilder gesperrt; Automatik wählt Standbild, Textseiten oder Laufschrift.
- Native Übergangseffekte: Einschieben, Regen, Fontäne, Blinken, Laser, Jalousien,
  Mosaik, Raute und weitere. Laufschrift bietet nur passende Links-/Rechts-Effekte.
  Effekt und Darstellung werden mit Vorlagen und RSS-Einstellungen gespeichert.
- Frei eintragbare RSS- und Atom-URLs, Feedprüfung und Schlagzeilenvorschau.
- Automatik mit 5–1440 Minuten Aktualisierungsintervall und bis zu 10 Schlagzeilen.
- Quellen werden abwechselnd berücksichtigt. Fehler einer Quelle blockieren andere nicht.
- Eine manuelle Textsendung pausiert RSS, damit der Text nicht kurz danach ersetzt wird.
- Verbindungsstatus, bestätigte Sendeaufträge und Fehlerprotokoll.

## Betrieb

Python-Server und Pillow laufen ausschließlich auf dem Raspberry; PowerLED und Windows
werden nicht benötigt. Der Server läuft als systemd-Benutzerdienst des installierenden Benutzers.

```sh
systemctl --user status tf-c2-web
systemctl --user restart tf-c2-web
journalctl --user -u tf-c2-web -n 80
tail -80 ~/tf-c2-web/data/service.log
```

SQLite-Datenbank und letztes Anzeigeprogramm liegen in `data/`. Dieses Verzeichnis für
eine Sicherung kopieren. Die Datenbank verwendet WAL; für eine Dateisicherung den Dienst
kurz stoppen oder die SQLite-Backupfunktion verwenden.

Die Oberfläche ist für das eigene Heimnetz ohne Login ausgelegt. Es gibt keine
Cloud-Verbindung und keine automatische Freigabe am Router. RSS-Abfragen erfolgen nur
für eingetragene öffentliche HTTP-/HTTPS-Quellen. Zugangsdaten in Feed-URLs, interne
Netzadressen, XML-Entities und Antworten über 2 MiB werden abgelehnt.

## Protokoll und Grenzen

Die globale Displayhelligkeit ist in 16 Hardwarestufen einstellbar. Der Regler liest
die aktuelle Stufe vom Controller; Loslassen schaltet auf manuelle Helligkeit um.
Native PowerLED-Referenz: `0x20`, Unterbefehl 2, aktueller 112-Byte-Parameterblock,
nur Offset 80 (Stufe 0–15) und 81 (manuell = 1) werden geändert. Alle übrigen Bytes
bleiben erhalten. Bestätigung und vollständiges Zurücklesen sind erforderlich.
Nach diesem Befehl pausiert die Controllerkommunikation kurz.

Texte unterstützen Schwarz und sieben Hintergrundfarben. LED-Rahmen sind optional
durchgehend, gestrichelt oder gepunktet, in eigener Farbe und mit 1 oder 2 Pixel
Stärke verfügbar. Rahmen und ein Pixel Innenabstand werden beim Umbruch und der
Schriftgrößenprüfung abgezogen; Logos werden auf den Innenbereich skaliert.
Mit Rahmen sind Standbild und Textseiten verfügbar, ohne Rahmen auch Laufschrift.
Die Gestaltung wird mit Vorlagen und Timeline-Szenen gespeichert.

Das Programmformat wurde anhand erfolgreicher PowerLED-Übertragungen ermittelt und am
angeschlossenen Controller getestet. Die 576 Byte Programmstruktur vor den Anzeigeseiten
stammen aus `image-template.bin`. Seiten bestehen aus 24 Byte Header und drei Bitplanes
mit je 512 Byte. Die Seiten sind über absolute Offsets verkettet. Pixel laufen zeilenweise
mit dem niederwertigsten Bit zuerst. Der Encoder verändert keine Hardware-, Scan- oder
Panelparameter und prüft diese nach jeder Übertragung erneut.

Die Farbplanes dieses Panels sind R/B/G angeordnet. Der Encoder tauscht Grün und Blau
beim Packen; Textfarben und Vorschau verwenden weiterhin normales RGB.
Verfügbar sind Rot, Grün, Blau, Gelb, Cyan, Magenta und Weiß. Das geprüfte Format
verwendet pro Farbkanal ein Bit; feinere Farbabstufungen sind nicht nachgewiesen.

Kommandos: `0x12` Firmware lesen, `0x21` Parameter lesen, `0xc1` Identifikation,
`0x14` Übertragung vorbereiten, `0x13` Datenblöcke mit Offset senden, `0x15/5` Programm
abschließen und starten. Die Abschlussprüfsumme ist `~sum(program) & 0xffffffff`.
Alle Datenpakete benötigen bestätigte Antworten mit gültiger 16-Bit-Prüfsumme.

Effektkorrektur: Der TF-C2-Seitenheader enthält bei +8 den Ausgangsmodus und bei +9
den tatsächlichen Effekt. Die Zuordnung der 47 PowerLED-GUI-Aktionen wurde anhand
eines nativen PowerLED-2.89.4-Programms für Firmware 0.5.9 erfasst. Referenz:
`native-effect-reference.json`. Die Gerätecodes unterscheiden sich ab GUI-Aktion 6
von den GUI-Indizes. Keine angebotene feste Auswahl schreibt den Zufallscode 0.
Ältere Vorlagen mit `effect=random` werden auf direkte Anzeige umgestellt.

Bis zu 2000 Zeichen und 120 Anzeigeseiten je Programm. Übertragungsdauer hängt von der
Anzahl der Seiten ab. Ein neuer Auftrag ersetzt das bisherige Anzeigeprogramm.
Die verfügbaren Farben hängen von den physischen LED-Modulen ab.

```sh
cd ~/tf-c2-web
.venv/bin/python -m unittest -v test_control.py
```

Für Hardwarediagnose bleibt `~/tf-c2-diagnostics/tf_c2_probe.py` verfügbar.
