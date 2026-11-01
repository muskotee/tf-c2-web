# Versionshinweise

## 1.1.2 — 2026-11-01

Bahnhofsuhr: Die nativen roten Zeigerparameter bleiben unverändert. Die vorherige
Farbanpassung verursachte wandernde Striche; das Rücksetzen wurde am Display als
störungsfrei bestätigt. Die Fenstergeometrie ist auf 32 Pixel ausgerichtet.
Rechts stehen jetzt Uhrzeit und aktuelles Datum in zwei getrennten, zentrierten
96×16-Fenstern. Eine bereits aktive Bahnhofsuhr wird beim Update neu übertragen.
47 Tests einschließlich Zeigerparametern, Zentrierung, Datumsposition und Migration.

## 1.1.1 — 2026-11-01

Korrektur für schwarze Uhranzeigen am realen TF-C2: Die vom Controller bestätigte
Übertragung eines Uhrprogramms mit eingebetteter Schrift ergab kein sichtbares
Bild. Auch eine unveränderte PowerLED-Referenz mit dieser Schrift blieb schwarz;
die Standarduhr mit eingebauter Schrift wurde dagegen sichtbar/laufend bestätigt.
Die verfügbaren Uhren verwenden deshalb nur die eingebaute Schrift. Angehängte
Schriftressourcen und ihr Verweis bei Offset 72 werden entfernt. Ein Regressionstest
vergleicht die rote Digitaluhr bytegenau mit der sichtbar bestätigten Referenz.
Binär-/Pac-Man-Ziffern sind vorerst deaktiviert und werden vom API abgelehnt.
Die Tafelvariante verwendet normale Ziffern mit Rahmen. 44 Tests insgesamt.

## 1.1.0 — 2026-11-01

Neue eigenständige Anzeigequelle Uhr & Datum mit sechs Stilen: digital,
Segmenttafel, BCD-Binärpunkte, Pac-Man-Ziffern, analog + digital und Weltzeit.
Drei native Datumsformate, Farben und Zeitzonen. Sekunden laufen direkt auf dem
Controller. Ein kurzer RTC-Abgleich pro Minute ersetzt regelmäßige Programmuploads.
Weltzeitversätze berücksichtigen unterschiedliche Sommerzeitwechsel. Beim Beenden
der Uhr lässt sich die vorherige Anzeige wiederherstellen. Acht zusätzliche Tests
(insgesamt 42), native Referenzvorlagen und separate Uhr-Dokumentation.

## 1.0.0 — 2026-11-01

Erstes Veröffentlichungspaket der am TF-C2 V6 getesteten Websteuerung.
Enthält Texte, gemischte Schriftgrößen, sichtbare vertikale Zentrierung,
Hintergrundfarben, LED-Rahmen, Logos, feste Effekte, RSS, Szenenstudio,
Hardwarehelligkeit, Installationsskript, systemd-Dienst und 34 Tests.

Das Paket ergänzt konfigurierbare USB-Gerätepfade und lokale Hostnamen. Der
Installationsdienst verwendet das Home-Verzeichnis des installierenden Benutzers.
Encoderstand: 3. Keine persönlichen Displayinhalte im Auslieferungsumfang.
