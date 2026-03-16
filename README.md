# Lab 2 – Container Security

Praktiskt flöde för container-hardening: bygg en sårbar baseline, scanna med Trivy, härda imagen, verifiera förbättringen och enforcea säkerhetspolicies i Kubernetes med OPA Gatekeeper.

## Vad projektet demonstrerar

- Medvetet sårbar image som baseline för Trivy-scanning
- Härdad image med reducerad attackyta, non-root och pinnade beroenden
- Trivy-rapport med tydlig före/efter-jämförelse
- SBOM i CycloneDX-format för supply chain-spårbarhet
- OPA Gatekeeper-policies som blockerar felaktiga deployer i klustret
- Cosign-signering för att verifiera image-integritet

---

## Säkerhetsbeslut – motivering

### Non-root user i härdad image
Processer som körs som root i en container ärver root-behörighet om containern breakas ut. En dedikerad systemanvändare (`appuser`) utan login-shell minskar konsekvenserna av en kompromiss — en angripare som tar sig in i applikationen kan inte eskalera till root-nivå i containern utan ytterligare exploatering. Non-root är ett krav i många härdade klustermiljöer och en grundkontroll i CIS Docker Benchmark.

### Slim base image med pinnad patch-version
`python:3.12-slim-bookworm` väljs framför full Python-image av två skäl: slim-varianten exkluderar kompilatorer, pakethanterare och systembibliotek som sällan behövs i runtime men utökar attackytan kraftigt. Pinning på patch-nivå (`3.12-slim-bookworm`) garanterar att exakt samma image används i alla byggkörningar — `latest` eller enbart majortag ger icke-deterministiska byggen där säkerhetsläget kan förändras utan att koden ändras.

### Trivy-scanning som verifieringssteg
Scanning körs på både sårbar och härdad image för att ge mätbar effekt av hardening-arbetet. Att ha en baseline utan scanning gör det omöjligt att veta vad härdningen faktiskt åstadkom. HIGH/CRITICAL är de kategorier som aktivt utnyttjas i produktion — dessa minskade från 37 till 4 totalt (OS + Python), vilket ger ett kvantifierbart säkerhetsutfall att kommunicera.

### SBOM i CycloneDX-format
En Software Bill of Materials anger exakt vilka komponenter och versioner som finns i imagen. Utan SBOM är det tidskrävande att avgöra påverkan när nya CVE:er publiceras — med SBOM kan man direkt filtrera på komponentnamn. CycloneDX väljs för brett verktygs- och plattformsstöd. SBOM:en arkiveras som `sbom.json` i repot och kan kopplas till signaturen för full supply chain-spårbarhet.

### OPA Gatekeeper-policies som admission control
Manuella säkerhetskrav i deployment-processer är opålitliga — de glöms bort eller kringgås. Gatekeeper enforcar kraven automatiskt vid varje `kubectl apply` via Kubernetes admission controller. Tre policies valdes för att täcka de vanligaste riskerna: saknad spårbarhet (labels), icke-reproducerbar image (`:latest`-tagg) och obegränsad resursförbrukning (resource limits). Policies definieras som kod i `policies/` och versionshanteras med resten av projektet.

### Cosign-signering med GitHub Secrets
En image i ett registry kan ersättas av en angripare med skrivrättigheter utan att det syns. Cosign skapar en kryptografisk signatur kopplad till image-digestet — verifiering vid deploy bekräftar att imagen inte modifierats sedan signering och att den kommer från rätt avsändare. `--yes` skickar signaturen till Rekor, en oföränderlig publik logg, vilket ger extern verifierbarhet utan tillgång till privatnyckeln. I CI/CD-pipelinen hanteras privatnyckeln som GitHub Secret (`COSIGN_PRIVATE_KEY`) — samma princip som `GCP_SA_KEY` i Lab 1. Nyckeln avkodas till en temporär fil, används för signering och raderas direkt efter. Ingen privat nyckel finns i repot eller exponeras i loggar.

---

## Kom igång

### Bygg sårbar image

```bash
docker build --no-cache --progress=plain -f Dockerfile.vulnerable -t lab2-vuln .
```

### Bygg härdad image

```bash
docker build --no-cache --progress=plain -f Dockerfile.hardened -t lab2-hardened .
```

### Kör lokalt (valfritt)

```bash
docker run --rm -p 5000:5000 lab2-hardened
```

Appen exponeras på `http://localhost:5000`.

---

## Trivy-scanning (G-krav)

### Baseline – sårbar image

```bash
trivy image lab2-vuln
trivy image --format json --output trivy-vulnerable.json lab2-vuln
```

Resultat (från `docs/scan-before.txt`):

- OS-paket: 228 vulnerabilities (UNKNOWN: 5, LOW: 114, MEDIUM: 73, HIGH: 31, CRITICAL: 5)
- Python-paket: 21 vulnerabilities (LOW: 3, MEDIUM: 12, HIGH: 6)

### Efter hardening – härdad image

```bash
trivy image lab2-hardened
trivy image --format json --output trivy-hardened.json lab2-hardened
```

Resultat (från `docs/scan-after.txt`):

- OS-paket: 113 vulnerabilities (UNKNOWN: 1, LOW: 91, MEDIUM: 17, HIGH: 2, CRITICAL: 2)
- Python-paket: 3 vulnerabilities (LOW: 2, MEDIUM: 1)

### Jämförelse

| Kategori | Före | Efter | Minskning |
|----------|------|-------|-----------|
| HIGH (OS) | 31 | 2 | −94 % |
| HIGH (Python) | 6 | 0 | −100 % |
| CRITICAL (OS) | 5 | 2 | −60 % |
| Totalt (alla) | 249 | 116 | −53 % |

---

## Hardening (G-krav)

`Dockerfile.hardened` använder ett **multi-stage build** med ett builder-steg och ett runtime-steg:

**Builder-steg**
- Installerar Python-beroenden med `pip install --prefix` till en isolerad katalog
- pip och build-verktyg stannar i builder-steget och når aldrig runtime-imagen

**Runtime-steg**
- `python:3.12-slim-bookworm` — nyare och avsevärt mindre base image
- Pinnad patch-version — reproducerbart och förutsägbart säkerhetsläge
- Non-root systemanvändare (`appuser`) skapas _innan_ några filer kopieras — korrekt ägandeskap från start
- Enbart beroenden kopieras från builder — ingen pip i slutbilden
- `COPY --chown` — korrekt filägande utan extra chmod-steg
- `CMD ["python", "app.py"]` utan shell — reducerar command-injection-yta
- `HEALTHCHECK` — möjliggör automatisk detektering av en hängande container

**`.dockerignore`** förhindrar att `cosign.key`, dokumentation och repo-metadata skickas in i build-contexten.

---

## SBOM (G-krav)

```bash
trivy image --format cyclonedx --output sbom.json lab2-hardened
```

- [x] `sbom.json` finns i repo
- Innehåller `metadata.component.name = "my-app:hardened"` med alla beroenden listade

---

## Gatekeeper / OPA Policies (VG)

Policies deployas i Mission Control → Gatekeeper Lab i namespace `sidestep-error`.

### Valda policies

| Policy | ConstraintTemplate | Constraint | Syfte |
|--------|--------------------|------------|-------|
| Require Labels | `require-labels-template.yaml` | `require-app-label.yaml` | Pods måste ha `app`-label för spårbarhet |
| Block :latest Tag | `block-latest-tag-template.yaml` | `block-latest-tag.yaml` | Blockerar `:latest` och saknad tagg |
| Require Resource Limits | `require-resource-limits-template.yaml` | `require-resource-limits.yaml` | Kräver `cpu` och `memory` limits |

Extra: `require-team-label.yaml` kräver även `team`-label.

### Applicera via kubectl

```bash
kubectl apply -f policies/require-labels-template.yaml
kubectl apply -f policies/require-app-label.yaml
kubectl apply -f policies/block-latest-tag-template.yaml
kubectl apply -f policies/block-latest-tag.yaml
kubectl apply -f policies/require-resource-limits-template.yaml
kubectl apply -f policies/require-resource-limits.yaml
```

### Verifiering

- [x] Bad Pod ger violations (screenshot: `screenshots/gatekeeper-deny.png`)
- [x] Hardened Pod passerar (screenshot: `screenshots/gatekeeper-pass.png`)

> **Notering:** Varningen `[no-default-sa] Using the default service account is not allowed` kommer från en aktiv klusterpolicy, inte från egna policies. Sätt `serviceAccountName` i Pod-spec för att åtgärda den.

### Rekommenderat Pod-manifest

`allowPrivilegeEscalation: false` förhindrar att SUID-binärer eller systemanrop eskalerar privilegier inifrån containern, även om non-root redan är satt. Det är ett komplement till `runAsNonRoot` och ett krav i CIS Kubernetes Benchmark.

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: app-sa
---
apiVersion: v1
kind: Pod
metadata:
  name: hardened-test
  labels:
    app: hardened-test
    team: sidestep-error
spec:
  serviceAccountName: app-sa
  containers:
    - name: app
      image: gcr.io/chas-devsecops-2026/jonitsx-app:v1
      securityContext:
        runAsNonRoot: true
        allowPrivilegeEscalation: false
      resources:
        limits:
          cpu: "200m"
          memory: "256Mi"
```

---

## Cosign-signering (VG)

```bash
cosign generate-key-pair
docker tag lab2-hardened gcr.io/chas-devsecops-2026/jonitsx-app:v1
docker push gcr.io/chas-devsecops-2026/jonitsx-app:v1
cosign sign --key cosign.key --yes gcr.io/chas-devsecops-2026/jonitsx-app:v1
cosign verify --key cosign.pub gcr.io/chas-devsecops-2026/jonitsx-app:v1
```

`--yes` skickar automatiskt signaturen till Rekor transparency log — en oföränderlig publik logg över signeringar. Det ger extern verifierbarhet utöver det lokala nyckelparet: vem som helst kan bekräfta att en signering skett vid en given tidpunkt utan att ha tillgång till privatnyckeln.

Utfall dokumenterat i `docs/cosign_logg.md`.

- [x] Image pushad till registry
- [x] Signering genomförd
- [x] Verifiering godkänd

---

## CI/CD-pipeline

`.github/workflows/container-security.yml` automatiserar hela säkerhetsflödet:

```
scan ── publish (main only)
 │
 ├── build image
 ├── trivy scan (CRITICAL/HIGH gate, fixable only)
 ├── trivy full report (artifact)
 ├── generate SBOM (artifact)
 └── save image (artifact)

publish:
 ├── load image (exakt samma som scannades)
 ├── push to GCR
 ├── sign with Cosign → Rekor
 └── verify signature
```

`scan` körs på alla triggers (PR och push). `publish` körs bara vid push till `main` eller manuell trigger.

### Secrets som krävs

| Secret | Beskrivning |
|--------|-------------|
| `GCP_SA_KEY` | Service account-nyckel för GCR-autentisering |
| `COSIGN_PRIVATE_KEY` | `cosign.key` base64-kodad: `base64 -w0 cosign.key` |
| `COSIGN_PASSWORD` | Lösenordet som sattes vid `cosign generate-key-pair` |

---

## Reflektion (G-krav)

Se [docs/reflection.md](docs/reflection.md).

---

## Säkerhetsstrategi (VG)

Se [docs/security_strategy.md](docs/security_strategy.md).

---

## Repo-struktur

```text
lab2-container-security/
├── .github/
│   └── workflows/
│       └── container-security.yml
├── Dockerfile.vulnerable
├── Dockerfile.hardened
├── app.py
├── requirements.txt
├── cosign.pub
├── sbom.json
├── policies/
│   ├── block-latest-tag-template.yaml
│   ├── block-latest-tag.yaml
│   ├── require-app-label.yaml
│   ├── require-labels-template.yaml
│   ├── require-resource-limits-template.yaml
│   ├── require-resource-limits.yaml
│   └── require-team-label.yaml
├── screenshots/
│   ├── gatekeeper-deny.png
│   └── gatekeeper-pass.png
├── docs/
│   ├── cosign_logg.md
│   ├── reflection.md
│   ├── scan-before.txt
│   ├── scan-after.txt
│   └── security_strategy.md
└── README.md
```

---

## Dokumentation

- [Reflektion](docs/reflection.md)
- [Säkerhetsstrategi](docs/security_strategy.md)
- [Cosign-logg](docs/cosign_logg.md)
