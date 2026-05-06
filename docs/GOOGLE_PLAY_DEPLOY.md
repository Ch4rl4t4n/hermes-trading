# Google Play (TWA) — Hermes web dashboard

Preparation for publishing **https://letagentscook.lol** as an Android app via **Trusted Web Activity (TWA)** or a PWA wrapper.

## Prerequisites

1. **HTTPS** on the production domain (required for PWA).
2. **Digital Asset Links** — file at `https://letagentscook.lol/.well-known/assetlinks.json`.
   - Repo: `dashboard/static/.well-known/assetlinks.json`
   - Replace `sha256_cert_fingerprints` with your **upload** or **Play App Signing** certificate SHA-256 after you create the Android app.
3. **Google Play Developer** account.
4. **Package name** used in this repo: `lol.letagentscook.hermes` (change consistently in `assetlinks.json` and Bubblewrap).

## Verify PWA

1. Android Chrome → open the site → **Install app** or use the install banner.
2. Confirm **standalone** (no browser URL bar).
3. Lighthouse PWA audit (target score 90+).

## Update asset links

```bash
keytool -list -v -keystore your-release.keystore -alias your_alias
```

Paste the SHA-256 into `assetlinks.json`, deploy, then:

```bash
curl -sS https://letagentscook.lol/.well-known/assetlinks.json
```

## Bubblewrap (recommended)

```bash
npm install -g @bubblewrap/cli
bubblewrap init --manifest=https://letagentscook.lol/static/manifest.json
bubblewrap build
```

Complete the wizard (package id, launcher name, keystore). Open the generated project in Android Studio, test on device, upload **.aab** to Play Console.

### Alternative: community PWA → APK tools

Some teams use experimental wrappers (e.g. `pwa2apk`-style flows). Prefer Bubblewrap for TWA compliance and Digital Asset Links. Example pattern:

```bash
npx @nicolo-ribaudo/pwa2apk https://letagentscook.lol
```

Verify the output uses the same **package name** and signing key you declare in `assetlinks.json`.

## Play Console

- Privacy policy URL, data safety, content rating, screenshots.
- Prefer **Android App Bundle** uploads.

## Push notifications

Background Web Push requires VAPID keys and a server endpoint to send notifications. Hermes ships a stub `push` handler in `sw.js`; full integration is future work.

## References

- https://developer.chrome.com/docs/android/trusted-web-activity/
- https://developers.google.com/digital-asset-links/v1/getting-started
- https://github.com/GoogleChromeLabs/bubblewrap
