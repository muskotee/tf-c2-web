# Betrieb, Sicherung und Fehlerbehebung

## Dienst

```sh
systemctl --user status tf-c2-web
systemctl --user restart tf-c2-web
journalctl --user -u tf-c2-web -n 80
tail -80 ~/tf-c2-web/data/service.log
```

## Sicherung

Die SQLite-Datenbank, Logos und zuletzt übertragene Programme liegen in `data/`.
Für eine konsistente Sicherung den Dienst kurz stoppen:

```sh
systemctl --user stop tf-c2-web
tar -czf "$HOME/tf-c2-backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$HOME/tf-c2-web" data config.env
systemctl --user start tf-c2-web
```

Sicherungsdateien enthalten persönliche Inhalte und gehören nicht ins öffentliche
Repository. Eine leere Installation erzeugt ihre Datenbank automatisch.

## Update

Dienst stoppen, `data/` und `config.env` sichern und behalten. Neue Quellcodedateien
an derselben Stelle entpacken; `config.env` nicht durch das Beispiel ersetzen.
Abhängigkeiten installieren, Tests ausführen und Dienst neu starten:

```sh
cd ~/tf-c2-web
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -q test_control.py
systemctl --user restart tf-c2-web
```

## Typische Probleme

- Display antwortet nicht: Stromversorgung, COM-Kabel, USB-Gerätepfad und Mitgliedschaft
  in `dialout` prüfen. Kein zweites Programm darf denselben Port verwenden.
- Zugriff verweigert: nach Ergänzung von `dialout` neu anmelden und neu starten.
- Webseite nicht erreichbar: Dienststatus, Pi-Adresse, Port und LAN-Verbindung prüfen.
  Zusätzliche lokale Hostnamen/IPs über `TF_ALLOWED_HOSTS` erlauben.
- Alte Oberfläche sichtbar: Browser mit Strg+F5 neu laden.
- Andere Farben: dieses Paket ist für die getestete R/B/G-Plane-Reihenfolge ausgelegt.
  Die Controller-Scanparameter nicht versuchsweise ändern.
- Text passt nicht: Automatik oder Textseiten verwenden, Schrift verkleinern oder
  Rahmenstärke reduzieren. Rahmen und Logos verringern den Textbereich.

## Deinstallation

```sh
systemctl --user disable --now tf-c2-web
rm "$HOME/.config/systemd/user/tf-c2-web.service"
systemctl --user daemon-reload
```

Die Programmdateien und `data/` bleiben dabei erhalten.
