#!/bin/bash
# First-boot script for an Amazon Linux 2023 instance (EC2 user data; runs once as root).
# Installs Docker and git, clones the public repo, builds and starts the app.
# Progress and errors are in /var/log/cloud-init-output.log.
set -euxo pipefail
dnf install -y docker git
systemctl enable --now docker
git clone https://github.com/AhmedMuhsen/pitwall.git /opt/pitwall
cd /opt/pitwall
./deploy/deploy.sh
