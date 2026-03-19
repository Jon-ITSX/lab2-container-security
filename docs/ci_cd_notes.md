# CI/CD Notes — ChasAcademy DevSecOps 2026

Praktiska lärdomar och kommandon från Lab 1 och Lab 2. Avsett som referens för framtida projekt i samma GCP-miljö.

---

## GCP-miljö

| Parameter            | Värde                                                            |
|----------------------|------------------------------------------------------------------|
| GCP-projekt          | `chas-devsecops-2026`                                            |
| Team/namespace       | `sidestep-error`                                                 |
| Artifact Registry    | `europe-north1-docker.pkg.dev/chas-devsecops-2026/student-apps/` |
| Image-namnkonvention | `jonitsx-app` (studentprefix + appnamn)                          |

---

## Auth mot Artifact Registry (GitHub Actions)

**Använd detta mönster — bekräftat fungerande:**

```yaml
- uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.GCP_SA_KEY }}

- run: gcloud auth configure-docker europe-north1-docker.pkg.dev --quiet

- run: docker push europe-north1-docker.pkg.dev/chas-devsecops-2026/student-apps/jonitsx-app:${{ github.sha }}
```

**Undvik `docker/login-action` med `_json_key`** — ger `artifactregistry.repositories.uploadArtifacts denied` i denna miljö.

Om push misslyckas med permission-fel: kontakta instruktören och be om `roles/artifactregistry.writer` på SA:n.

---

## GitHub Secrets

| Secret               | Innehåll                     | Notering                                                   |
|----------------------|------------------------------|------------------------------------------------------------|
| `GCP_SA_KEY`         | Service account JSON         | Multiline — skicka alltid via env var, inte inline i shell |
| `COSIGN_PRIVATE_KEY` | `cosign.key` base64-kodad    | Se kodningskommando nedan                                  |
| `COSIGN_PASSWORD`    | Lösenord till cosign-nyckeln | **Inga specialtecken** — orsakar `decryption failed` i CI  |

### Koda cosign.key för GitHub Secrets

**PowerShell:**
```powershell
[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("C:\full\path\to\cosign.key"))
```

**Git Bash / Linux:**
```bash
base64 -w0 cosign.key
```

### Multiline secrets i shell (GCP_SA_KEY)

Expandera aldrig multiline secrets direkt i shell-kommandon — använd env var i steget:

```yaml
- name: Verify secrets
  env:
    GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}
  run: |
    test -n "$GCP_SA_KEY" || (echo "Missing GCP_SA_KEY" && exit 1)
```

---

## Cosign — image-signering

### Generera nycklar (Windows PowerShell)

```powershell
# Lösenord UTAN specialtecken — specialtecken orsakar decryption failed i CI
$env:COSIGN_PASSWORD = "EnkeltLösenord2026"
cosign generate-key-pair
```

### Signera lokalt

```powershell
$env:COSIGN_PASSWORD = "EnkeltLösenord2026"
cosign sign --key cosign.key --yes europe-north1-docker.pkg.dev/chas-devsecops-2026/student-apps/jonitsx-app:v1
```

```bash
# Git Bash / Linux
COSIGN_PASSWORD="EnkeltLösenord2026" cosign sign --key cosign.key --yes \
  europe-north1-docker.pkg.dev/chas-devsecops-2026/student-apps/jonitsx-app:v1
```

### Signera med digest (rekommenderat)

En tagg kan pekas om till en annan image — signaturen gäller då fel image. Signera alltid med digest:

```bash
# Hämta digest efter push
DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' IMAGE_REF)
cosign sign --key cosign.key --yes "$DIGEST"
```

I GitHub Actions-pipeline:
```yaml
- name: Push image and capture digest
  run: |
    IMAGE_REF="${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}"
    docker push "$IMAGE_REF"
    DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE_REF")
    echo "IMAGE_DIGEST=$DIGEST" >> $GITHUB_ENV

- name: Sign image
  env:
    COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
    COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
  run: |
    echo "$COSIGN_PRIVATE_KEY" | base64 -d > /tmp/cosign.key
    cosign sign --key /tmp/cosign.key --yes "${{ env.IMAGE_DIGEST }}"
    rm -f /tmp/cosign.key
```

### Verifiera signatur

```bash
cosign verify --key cosign.pub europe-north1-docker.pkg.dev/chas-devsecops-2026/student-apps/jonitsx-app:v1
```

---

## GitHub Actions — bra att veta

### Runners
Pinna till specifik version för reproducerbarhet:
```yaml
runs-on: ubuntu-24.04  # inte ubuntu-latest
```

### COSIGN_PRIVATE_KEY via env var (inte inline)
```yaml
# Rätt — undviker specialtecken-tolkningsproblem
- name: Sign image
  env:
    COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
  run: echo "$COSIGN_PRIVATE_KEY" | base64 -d > /tmp/cosign.key

# Fel — ${{ }} expanderas av Actions innan shell kör, kan tolka specialtecken
- run: echo "${{ secrets.COSIGN_PRIVATE_KEY }}" | base64 -d > /tmp/cosign.key
```

### Re-run triggar inte om workflow-filen ändrats
Re-run Jobs använder den ursprungliga commit-SHA:n. Pusha alltid en ny commit för att testa en workflow-fix.

### PR vs push till main
- PR triggar bara `scan`-jobbet (om publish är begränsat till `push: branches: [main]`)
- `publish`-jobbet triggas först när PR mergats till main

---

## OPA Gatekeeper (Mission Control)

- Policies deployas via Mission Control → Gatekeeper Lab, inte med `kubectl apply`
- YAML-filerna i `policies/` är dokumentation och referens — strukturen visas men deployas via UI
- Klustret har förinstallerade policies (`no-default-sa` etc.) som gäller alla studenter
- Skapa en dedikerad ServiceAccount i namespacet för att undvika `no-default-sa`-varningar

---

## Felsökning

| Fel                                                    | Trolig orsak                               | Lösning                                                     |
|--------------------------------------------------------|--------------------------------------------|-------------------------------------------------------------|
| `artifactregistry.repositories.uploadArtifacts denied` | SA saknar skrivrättigheter                 | Kontakta instruktör — be om `roles/artifactregistry.writer` |
| `decrypt: decryption failed` (cosign)                  | Specialtecken i `COSIGN_PASSWORD`          | Generera om nyckelpar med alfanumeriskt lösenord            |
| `test: too many arguments`                             | Multiline secret expanderas inline i shell | Skicka secret via env var i steget                          |
| `fetch first` vid git push                             | Remote har commits som saknas lokalt       | `git pull origin BRANCH` sedan push                         |
| Re-run ger samma fel efter workflow-fix                | Re-run använder ursprunglig SHA            | Pusha ny commit för att trigga ny körning                   |
