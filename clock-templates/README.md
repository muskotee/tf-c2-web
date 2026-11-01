# Native Uhrvorlagen

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
