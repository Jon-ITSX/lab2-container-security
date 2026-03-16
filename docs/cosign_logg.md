# Cosign-logg (VG)

## Bakgrund – vad är Rekor transparency log?

Rekor är en oföränderlig, publik logg för signeringsdata, driven av Sigstore-projektet. Den bygger på en **Merkle tree**-struktur där poster inte kan ändras eller raderas i efterhand utan att det syns.

När en image signeras med `--yes` skickas en loggpost till Rekor som innehåller:

- Image-digestet (`sha256:...`) — ett fingeravtryck av imagen
- Den **publika** nyckeln (`cosign.pub`) — privatnyckeln lämnar aldrig den lokala maskinen
- Signaturen — det kryptografiska beviset
- En notariellt bekräftad tidsstämpel

Det innebär att en tredje part kan verifiera att en specifik image signerades vid en viss tidpunkt — utan tillgång till privatnyckeln och oberoende av din egen infrastruktur. Det är skillnaden mot att enbart lagra signaturen i registryt: Rekor-posten är ett **oavvisbart externt kvitto**.

Praktiskt exempel: om en CVE publiceras och frågan uppstår "var imagen signerad och pushad _innan_ sårbarheten var känd?" kan Rekor-tidsstämpeln bevisa det — utan att du behöver hävda det på heder och samvete.

---

## 1. Registry och image

- Registry: `gcr.io/chas-devsecops-2026`
- Image: `gcr.io/chas-devsecops-2026/jonitsx-app`
- Tagg: `v1`
- Digest: `sha256:d8f9904fb911be85b8453ec95c5ad6908f29b87b33c212bbe6b97780bf3e6cc7`

## 2. Generera nycklar

Lösenordet sätts via miljövariabel — cosign v1.3.1 stöder inte interaktiv lösenordsinmatning i alla terminaler på Windows.

**PowerShell (Windows):**
```powershell
$env:COSIGN_PASSWORD = "<lösenord>"
cosign generate-key-pair
```

**Bash (Linux/macOS):**
```bash
export COSIGN_PASSWORD="<lösenord>"
cosign generate-key-pair
```

Resultat: `cosign.key` och `cosign.pub` skapades i projektmappen. Privatnyckeln (`cosign.key`) är tillagd i `.gitignore` och checkas inte in i repot. `cosign.pub` är committad och används som verifieringsreferens.

## 3. Tagga och pusha image

Kommandona är identiska på alla plattformar:

```bash
docker tag my-app:hardened gcr.io/chas-devsecops-2026/jonitsx-app:v1
docker push gcr.io/chas-devsecops-2026/jonitsx-app:v1
```

Resultat: imagen pushad till GCR utan fel.

## 4. Signera image

```bash
cosign sign --key cosign.key --yes gcr.io/chas-devsecops-2026/jonitsx-app:v1
```

`--yes` skickar automatiskt signaturen till Rekor transparency log. Se Bakgrund-sektionen ovan för vad som skickas och varför.

I CI/CD-pipelinen hanteras privatnyckeln via GitHub Secret (`COSIGN_PRIVATE_KEY`) — nyckeln avkodas från base64 till en temporär fil, signering körs och filen raderas direkt. Lösenordet injiceras via `COSIGN_PASSWORD`-secret, samma princip som `GCP_SA_KEY` i Lab 1.

Resultat: signeringen genomfördes utan fel.

## 5. Verifiera signatur

```bash
cosign verify --key cosign.pub gcr.io/chas-devsecops-2026/jonitsx-app:v1
```

Resultat:

```
Verification for gcr.io/chas-devsecops-2026/jonitsx-app:v1 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - The signatures were verified against the specified public key
  - Any certificates were verified against the Fulcio roots.

[{"critical":{"identity":{"docker-reference":"gcr.io/chas-devsecops-2026/jonitsx-app"},"image":{"docker-manifest-digest":"sha256:d8f9904fb911be85b8453ec95c5ad6908f29b87b33c212bbe6b97780bf3e6cc7"},"type":"cosign container image signature"},"optional":null}]
```

- Signaturen verifierad: [x] Ja

## 6. Koda privatnyckeln för GitHub Secrets

För att lägga upp `COSIGN_PRIVATE_KEY` som GitHub Secret behöver nyckeln vara base64-kodad:

**PowerShell (Windows):**
```powershell
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("cosign.key"))
```

**Bash (Linux/macOS):**
```bash
base64 -w0 cosign.key
```

Kopiera hela outputen och lägg till som repository secret under:
**Settings → Secrets and variables → Actions → New repository secret**
