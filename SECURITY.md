# Security

Audio Station is a private single-user application. Bind to loopback or a specific private interface and apply host firewall/access controls. Do not expose the controller, Applio, or Docker gateway publicly. The gateway's token is generated locally and must never be committed or posted in issues.

The gateway has host-administration power through the Docker socket. Only shipped fixed provisioning/actions are exposed. Treat reviewed controller images, build contexts, and configuration as trusted administration code. Do not add arbitrary image/command/path/URL parameters to these APIs. Downloaded model formats can carry executable behavior; only approved publisher files with reviewed checksums are in the catalogue.

For a vulnerability, contact the repository maintainer privately using GitHub private vulnerability reporting if enabled. Do not include credentials, private audio, or exploit details in a public issue. Maintainers must enable a private reporting channel before public release.
