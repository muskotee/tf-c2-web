# Native Uhrvorlagen

`playlist-single.bin`, `playlist-two.bin` und `playlist-three.bin` sind zusätzliche
PowerLED-Referenzen mit festgelegten Laufzeiten 5/7/9 Sekunden. `programs.merge`
reproduziert die Zwei- und Drei-Programm-Dateien bytegenau aus der Einzelreferenz.
Der globale Kopf ist 128 Byte groß; Anzahl bei +120, Verzeichnisprüfbytes bei
+125/+127, danach je Programm ein absoluter 32-Bit-Zeiger. Ein Programmkopf ist
444 Byte groß; die Fenstertabelle beginnt relativ bei +216. Alle Fenster- und
Seitenverkettungszeiger werden beim Zusammenstellen neu adressiert. Native Uhren
verwenden eine feste Programmlaufzeit; Textprogramme spielen ihre Seiten einmal
vollständig ab. Es erfolgt keine neue Übertragung bei jedem Szenenwechsel.

**Kompatibilitätsbefund vom Display:** Die unveränderte PowerLED-Standarduhr mit
eingebauter Schrift ist sichtbar und läuft. Schon die unveränderte Vorlage mit
angehängter benutzerdefinierter Schrift bleibt schwarz. Die erfolgreiche
Paketbestätigung prüft dies nicht. Ab 1.1.1 werden deshalb nur die eingebauten
Uhrschriften verwendet; angehängte Schriftblöcke werden vor dem Upload entfernt.
Binär- und Arcade-Ziffern sind gesperrt. Die Dateien bleiben Erfassungsreferenzen.
`standard.bin` ist die vom Nutzer als sichtbar/laufend bestätigte rote Standarduhr.
Der digitale Kompatibilitäts-Upload wird bytegenau dagegen getestet. Beim Entfernen
angehängter Schriften muss zusätzlich der Schriftverweis bei Offset 72 auf null
gesetzt werden; ein verbleibender Verweis zeigt hinter das verkürzte Programm.

Die Bahnhofsuhr wird für die eingebaute Schrift neu aufgebaut: Zifferblatt
32×32 bei (0,0), Uhrzeitfenster 96×12 bei (32,4), Datumsfenster 96×10 bei (32,19).
Die 48 Pixel breite Uhrzeit beginnt relativ bei x=24. Das Datum ist ein eigener
Rasterbereich mit einer festen 6-Pixel-Zeichenbreite; die nicht zuverlässig
umgesetzte native Datumsformat-Auswahl wird nicht mehr für die Ausgabe verwendet.
Mit Logo wird ein zusätzlicher 32×32-Rasterbereich links oder rechts neben dem
Text reserviert; der Textbereich der Bahnhofsuhr ist dann 64 Pixel breit.
Dadurch sind die Fenster auf 32 Pixel ausgerichtet, überlappen sich nicht und
die beiden Zeilen liegen mittig im rechten Bereich. Die Zeigerparameter bleiben
bytegenau auf den unveränderten roten Standardwerten: Änderungen führten am
realen Display zu wandernden Strichen; die Rückkehr zu diesen Werten wurde vom
Nutzer als störungsfrei bestätigt. Digitale Seitenheader und leere Raster werden neu angelegt; die alte
36/72-Pixel-Geometrie der PowerLED-Referenz wird nicht weiterverwendet.

Aus PowerLED 2.89.4 erfasste Programmstrukturen für TF-C2 V6 / Firmware 0.5.9.
Die Erfassung erfolgte über eine UDP-Antwortsimulation ohne serielle Schreibzugriffe.
Die Anwendung passt Farben, Datumsformat, Ziffernbitmaps und Weltzeitversatz an.

- digital.bin: eine native Zeitfläche (Seitentyp 11), benutzerdefinierte Schrift.
- date.bin: eine native Datumsfläche, große Schrift.
- compact.bin: Datum und Zeit in zwei Zeilen, kompakte Schrift.
- analog.bin: analoges Zifferblatt (Typ 10) und digitale Zeitfläche.
- world.bin: zwei Zeitflächen mit gemeinsamem eingebettetem Schriftatlas.

Fenstertabelle: Offset 348, Einträge mit 12 Byte (`<IHHHH`: Seite, x, y, Breite,
Höhe). Die Rasterzeilen sind auf 32 Pixel ausgerichtet. Native Seitendaten beginnen
mit einem 24-Byte-Header. Seitentyp steht bei +7. Typ 11: Schriftindex und aktive
Inhalte bei +8, Text-x-Positionen bei +9 bis +12, Datumsformat bei +15 (niedrige
4 Bit), Farben bei +15 bis +17 (hohe 4 Bit), Zeitversatz in Minuten bei +18
(signed LE16). Native Datumsformate: 1 ISO, 4 kurzes ISO-Jahr, 11 Tag.Monat.Jahr.

Schriftatlas folgt den Rasterflächen; Magic `05 0a a5 5a`. Glyphen ab ASCII 33:
Tabelle ab +24 mit 8 Byte je Zeichen (`<IHH`: relativer Bitmapoffset, Breite, Höhe).
Glyphenraster sind zeilenweise, LSB zuerst, 0 = sichtbarer Pixel. Die alternativen
Ziffernschriften ersetzen ausschließlich die vorhandenen Bitmapbytes. Alle Längen,
Schriftkennungen und Zeiger bleiben erhalten.

RTC-Abgleich: Kommando 0x25, Payload `<II`: lokale Wanduhrzeit als Unix-artiger
Zeitstempel und ein Null-Dword. Ein UTC-Zeitstempel ohne Zeitzonenanpassung würde
auf diesem Controller die falsche lokale Uhrzeit anzeigen. Farben verwenden die
getestete R/B/G-Bitreihenfolge. Hardware-/Scanparameter werden nicht geschrieben.
