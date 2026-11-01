# Uhr und Datum

In der Seitenleiste **Uhr & Datum** öffnen, Gestaltung wählen und **Uhr am Display
starten** drücken. Beim Wechsel der Gestaltung erneut übernehmen. Einstellungen
bleiben auf dem Raspberry gespeichert. **Vorherige Anzeige** stellt die Anzeige
und RSS-Einstellung wieder her, die vor dem Start der Uhr aktiv waren.

## Darstellungen

**Kompatibilität ab 1.1.1:** Digital, gerahmte Tafel, analog + digital und Weltzeit
verwenden die eingebaute Uhrschrift. Binär- und Pac-Man-Ziffern sind vorerst
deaktiviert: Bereits unveränderte PowerLED-Uhrprogramme mit eingebetteter Schrift
blieben auf dem angeschlossenen TF-C2 schwarz. Die ursprüngliche Version 1.1.0
hatte nur die Übertragungsbestätigung geprüft, nicht die tatsächlich sichtbare
Uhr. Die Webvorschau ist für die eingebaute Controller-Schrift schematisch.

- **Digital:** klassische Ziffern mit Sekunden.
- **Börsentafel:** digitale Ziffern und ein farbiger Tafelrahmen.
- **Binär / BCD (derzeit gesperrt):** jede Dezimalziffer wird zur Punktspalte. Gewichte von oben nach
  unten: 8, 4, 2, 1. Gefüllte Felder addieren, hohle Felder bleiben aus. Zwei
  Spalten bilden jeweils Stunden, Minuten und Sekunden.
- **Arcade (derzeit gesperrt):** kleine Pac-Man-Ziffern mit gefressenen Punkten über jeder Ziffer.
  Die Sekunden-Einer starten alle zehn Sekunden neu. Dies ist eine Ziffernanimation,
  kein umlaufender 60-Sekunden-Rahmen.
- **Bahnhof:** analoge Uhr mit drei roten Zeigern, daneben die Uhrzeit und
  darunter das aktuelle Datum. Die kompatiblen Zeigerwerte bleiben unverändert;
  Ziffern- und Zifferblattfarbe lassen sich weiterhin wählen.
- **Weltzeit:** zwei digitale Uhren nebeneinander; die Städtenamen stehen in der
  Webansicht. Es werden keine echten Börsenkurse abgerufen.

Für Digital und die gerahmte Tafel stehen Uhrzeit, Uhrzeit plus Datum und Datum allein zur
Wahl. Datum: Tag.Monat.Jahr, ISO oder ISO mit kurzem Jahr. Die Bahnhofsuhr zeigt
Uhrzeit plus Datum, die Weltzeitansicht nur Uhrzeiten. Ziffernfarbe lässt sich wählen; Tafelrahmen
und analoge Uhr bieten zusätzlich eine Akzentfarbe.

## Uhr als Szene in einer Timeline

Die Uhr gestalten und **Als Uhrszene zur Timeline hinzufügen** wählen. Alternativ
im Szenenstudio **Uhrszene ＋** anklicken. Darstellung, Farben, Datum, Zeitzonen
und Logo werden mit der Szene gespeichert. Die Anzeigedauer ist für jede Uhrszene
von 2 bis 30 Sekunden einstellbar. Drag-and-drop, Bearbeiten, Duplizieren und
Rückgängig funktionieren wie bei Textszenen; Bearbeiten öffnet die Uhransicht.

Der Controller spielt die gesamte gemischte Folge selbstständig ab. Uhrsekunden
laufen während der Szene nativ weiter. Jede Szene verwendet ihre eigene
Fensteraufteilung. Eine neue Übertragung pro Szenenwechsel ist nicht nötig.
Der Raspberry gleicht die gemeinsame Controllerzeit einmal pro Minute ab;
unterschiedliche Zeitzonen werden in den einzelnen Uhrszenen berücksichtigt.
Beim lokalen Tageswechsel oder verändertem Sommerzeitversatz wird die Folge neu
übertragen, um Datumsbilder und Versätze zu aktualisieren. Dadurch beginnt die
Folge bei dieser gelegentlichen Aktualisierung wieder bei der ersten Szene.

## Logo und Datumsdarstellung

Unter **Logo bei der Uhr** ein vorhandenes Bild wählen oder ein neues hochladen.
Die Logo-Bibliothek ist dieselbe wie bei Textanzeigen. Links oder rechts neben der
Uhrzeit sind möglich. Ein Logo erhält einen eigenen 32×32-Pixel-Bereich und wird
proportional eingepasst. Bei der Bahnhofsuhr bleibt das Zifferblatt ganz links;
„Logo links“ bedeutet links neben Uhrzeit und Datum. Die zwei Weltzeituhren
belegen das gesamte Display; dort ist kein zusätzlicher Logo-Bereich verfügbar.

Die Firmware stellte trotz angewähltem Tag.Monat.Jahr weiterhin Jahr-Monat-Tag
dar. Deshalb wird das Datum jetzt auf dem Raspberry als fertiges Pixelbild
gerendert. Das gewählte Format erscheint damit tatsächlich als `01.11.2026`,
`2026-11-01` oder `26-11-01`. Unter der Uhrzeit verwendet das Datum eine feste
6-Pixel-Zeichenbreite mit sieben sichtbaren Pixelzeilen und einfachen LED-Strichen.
Datum allein wird größer dargestellt. Uhrzeit und Datum haben getrennte, vertikal
platzierte Bereiche; Datum und Logos entsprechen pixelgenau der Webvorschau.

## Zeitquelle und Betrieb

Die native Controlleruhr erzeugt die laufenden Sekunden. Der Browser muss nicht
geöffnet bleiben. Der Raspberry gleicht die Uhr beim Start und danach einmal pro
Minute ab. Pro Abgleich wird nur das kurze RTC-Kommando gesendet, kein neues
Anzeigeprogramm. Ein neuer Stil, ein veränderter Weltzeitversatz oder ein neuer
lokaler Kalendertag erfordert eine Programmübertragung. Das Datum wird beim
nächsten minütlichen Abgleich nach dem Tageswechsel neu gerendert. Unterbrechungen
der Raspberry-Verbindung stoppen die native Uhr nicht; ihr nächster Zeitabgleich
erfolgt nach Wiederverbindung. Ohne Raspberry bleibt das Datumsbild bis zum
nächsten erfolgreichen Abgleich auf seinem zuletzt übertragenen Tag stehen.

Zeitzonen: Berlin, London, UTC, New York und Tokio. Der Raspberry berechnet Sommer-
und Winterzeit aus seiner Zeitzonendatenbank. Unterschiedliche Umstellungstermine
der beiden Weltzeitzonen werden beim nächsten Abgleich berücksichtigt.

Der Raspberry sollte selbst eine korrekte Systemzeit haben (`timedatectl status`).
Eine vollständig stromlose Controlleruhr kann die Zeit abhängig von ihrer eigenen
RTC-Versorgung verlieren; nach dem Start wird sie erneut abgeglichen.

Uhrstart pausiert RSS. Eine manuelle Text-/Timeline-Sendung oder das Aktivieren von
RSS beendet den Uhrmodus. Helligkeitsänderungen lassen die Uhr weiterlaufen.
Die Uhr lässt sich einzeln oder als Szenentyp innerhalb einer Timeline verwenden.
Native Schrift- und Zeigerdarstellung kann sich geringfügig von der
Webvorschau unterscheiden.
