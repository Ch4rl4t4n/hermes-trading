# Hermes Node Runtime Upgrade (Frontend Build Gate)

Tento runbook rieši warning/fail na Vite runtime checku.

## Cieľ

- mať Node.js `>= 20.19.0` (alebo `>= 22.12.0`)
- prejsť strict pre-release gate:

```bash
cd /root/hermes
scripts/pre_release_checks_strict.sh
```

## 1) Skontroluj aktuálnu verziu

```bash
node -v
cd /root/hermes
scripts/check_frontend_node_version.sh
```

## 2) Upgrade Node.js na Ubuntu (NodeSource)

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Voliteľne (ak chceš Node 22):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

## 3) Verifikácia po upgrade

```bash
node -v
npm -v
cd /root/hermes
scripts/check_frontend_node_version.sh
```

Očakávanie:

- `OK: Node.js ... (requirement >= 20.19.0)`

## 4) Release gate (strict)

```bash
cd /root/hermes
scripts/pre_release_checks_strict.sh
```

Ak strict gate prejde, build + swarm smoke sú pripravené na release.
