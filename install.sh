#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(pwd -P)" != "$HOME/tf-c2-web" ]]; then
  echo 'Bitte das Paket zuerst nach ~/tf-c2-web entpacken und dort bash install.sh ausführen.' >&2
  exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
  echo 'Als normaler Raspberry-Pi-Benutzer ausführen, nicht mit sudo.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3 python3-venv fonts-liberation
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data "$HOME/.config/systemd/user"
if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  sudo usermod -aG dialout "$(id -un)"
  echo 'Serieller Zugriff hinzugefügt: nach der Installation abmelden und neu anmelden.'
fi
if [[ ! -f config.env ]]; then cp config.env.example config.env; fi
cp tf-c2-web.service "$HOME/.config/systemd/user/tf-c2-web.service"
.venv/bin/python -m unittest -q test_control.py test_clocks.py
systemctl --user daemon-reload
systemctl --user enable --now tf-c2-web.service
sudo loginctl enable-linger "$(id -un)"
echo 'Installiert. Aufruf: http://<IP-des-Raspberry>:8080/'
echo 'USB-Pfad und Hostnamen bei Bedarf in ~/tf-c2-web/config.env anpassen.'
