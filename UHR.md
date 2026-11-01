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

## Zeitquelle und Betrieb

Die native Controlleruhr erzeugt die laufenden Sekunden. Der Browser muss nicht
geöffnet bleiben. Der Raspberry gleicht die Uhr beim Start und danach einmal pro
Minute ab. Pro Abgleich wird nur das kurze RTC-Kommando gesendet, kein neues
Anzeigeprogramm. Lediglich ein neuer Stil oder ein veränderter Weltzeitversatz
erfordert eine Programmübertragung. Unterbrechungen der Raspberry-Verbindung
stoppen die native Uhr nicht; ihr nächster Zeitabgleich erfolgt nach Wiederverbindung.

Zeitzonen: Berlin, London, UTC, New York und Tokio. Der Raspberry berechnet Sommer-
und Winterzeit aus seiner Zeitzonendatenbank. Unterschiedliche Umstellungstermine
der beiden Weltzeitzonen werden beim nächsten Abgleich berücksichtigt.

Der Raspberry sollte selbst eine korrekte Systemzeit haben (`timedatectl status`).
Eine vollständig stromlose Controlleruhr kann die Zeit abhängig von ihrer eigenen
RTC-Versorgung verlieren; nach dem Start wird sie erneut abgeglichen.

Uhrstart pausiert RSS. Eine manuelle Text-/Timeline-Sendung oder das Aktivieren von
RSS beendet den Uhrmodus. Helligkeitsänderungen lassen die Uhr weiterlaufen.
Die Uhr ist eine eigene Anzeigequelle und derzeit keine Szenenart innerhalb der
Timeline. Native Schrift- und Zeigerdarstellung kann sich geringfügig von der
Webvorschau unterscheiden.
