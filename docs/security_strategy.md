# Säkerhetsstrategi – Lab 2 (Container Security)

Strategin i det här projektet bygger på att säkerhet tillämpas i varje steg av containerns livscykel — från bygge till körning i klustret — snarare än som ett enskilt kontrollsteg precis innan deploy. Det är samma grundprincip som i Lab 1: säkerhet ska vara inbyggd i processen, inte limmad på efteråt.

---

## Hotbild och kontroller

### Sårbara paket i image
Kända CVE:er i OS-paket och Python-bibliotek kan utnyttjas av en angripare som får kodexekvering i containern. Utan scanning är det omöjligt att veta vilken risknivå en image bär med sig. Trivy körs mot både sårbar och härdad image för att ge ett mätbart utfall — hur många HIGH/CRITICAL-fynd eliminerades av hardening-arbetet. Rapporten sparas som artefakt (`scan-before.txt`, `scan-after.txt`) och utgör bevis på att säkerhetsläget aktivt förbättrades.

### Ospårbara komponenter i leveranskedjan
Om en ny CVE publiceras för ett bibliotek måste man snabbt kunna avgöra om den påverkar en specifik image. Utan en komponentförteckning krävs manuell inspektion av varje image — tidskrävande och feltolerant. SBOM:en i CycloneDX-format (`sbom.json`) listar alla ingående komponenter med version och källa. Det gör det möjligt att automatisera CVE-matchning mot publicerade advisory-databaser och att snabbt avgöra påverkan utan att behöva inspektera imagen direkt.

### Felaktiga deploy-mönster i klustret
Manuella granskningar av Kubernetes-manifests skalas inte — det finns alltid risk att en pod deployas utan labels, med `:latest`-tagg eller utan resource limits. OPA Gatekeeper enforcar tre policies direkt i admission controller-lagret: pods utan `app`-label nekas, images utan explicit tagg nekas, och containers utan `cpu`/`memory`-limits nekas. Eftersom policies är definierade som kod i `policies/` är de versionshanterade och reproducerbara — ingen manuell konfiguration i klustret som kan tappas bort.

### Manipulerad eller obekräftad image i registry
En image i ett registry kan ersättas utan att det syns om ingen signaturkontroll finns. Det gör det möjligt för en angripare med skrivrättigheter i registryt att byta ut en legitim image mot en modifierad version. Cosign löser detta genom att skapa en kryptografisk signatur kopplad till image-digestet. Verifiering vid deploy bekräftar att imagen inte ändrats sedan signering och att den härstammar från rätt nyckel. `--yes` vid signering skickar automatiskt till Rekor transparency log — en oföränderlig publik logg som möjliggör extern verifiering utan tillgång till privatnyckeln. Privatnyckeln (`cosign.key`) checkas aldrig in i repot — i produktion hanteras den via KMS.

Signeringen i pipelinen använder ett **digest-referens** (`sha256:...`) snarare än en tagg. En tagg kan i teorin pekas om till en annan image efter signering — signaturen skulle då gälla en annan image än den som verifieras. Ett digest är en kryptografisk hash av exakt det image-innehåll som signerades och kan aldrig pekas om. Det gör signaturen obrytbart kopplad till rätt image.

---

## Principer

### Least privilege
Non-root-användare i `Dockerfile.hardened`, inga onödiga paket installerade, och `CMD` utan shell minskar angreppsytan om containern komprometteras. `allowPrivilegeEscalation: false` i Pod-manifestets `securityContext` blockerar privilegieeskalering via SUID-binärer eller systemanrop, även om containern körs som non-root. Resource limits i Gatekeeper-policies förhindrar att en komprometterad container förbrukar obegränsade klusterresurser.

### Multi-stage build och minimal build-kontext
`Dockerfile.hardened` använder ett builder-steg för att installera Python-beroenden och ett separat runtime-steg som enbart kopierar de färdiga paketen. pip och build-verktyg når aldrig slutbilden — de kan inte utnyttjas av en angripare som bryter sig in i containern. `.dockerignore` säkerställer att `cosign.key`, dokumentation och repo-metadata aldrig inkluderas i build-contexten, vilket eliminerar risken att känsliga filer råkar hamna i imagen.

### Reproducerbarhet
Explicita image-taggar på patch-nivå och pinnade Python-beroenden i `requirements.txt` garanterar att exakt samma komponentuppsättning byggs varje gång. `latest` och lösa versionsintervall ger icke-deterministiska byggen där säkerhetsläget kan förändras utan att koden ändras. Samma princip gäller för GitHub Actions-runners — pipelinen använder `ubuntu-24.04` i stället för `ubuntu-latest` för att garantera ett känt och förutsägbart exekveringsmiljö. En uppgradering av runner-OS ska vara ett medvetet val, inte en tyst bieffekt av att GitHub byter vad `latest` pekar på.

### Shift-left
Trivy-scanning körs mot imagen direkt efter bygge — inte som ett sent steg i en deploy-pipeline. Ju tidigare ett fynd identifieras, desto billigare är det att åtgärda. En CRITICAL i baseline som blockerar merge är billigare än samma CRITICAL som hittas i produktion.

### Policy-as-code
Säkerhetskrav som leverar som kod i `policies/` versionshanteras, granskas och deployas på samma sätt som applikationskod. Det eliminerar konfigurationsdrift och gör det möjligt att audita vilka krav som gäller vid varje given tidpunkt.

### Verifierbarhet
SBOM + Cosign-signatur tillsammans ger en verifierbar kedja: vad som är i imagen (SBOM) och att ingen har rört den sedan den byggdes (signatur). Det är grunden för supply chain-integritet.

---

## CI/CD-pipeline

Hela säkerhetsflödet är implementerat i `.github/workflows/container-security.yml` med två jobb:

**`scan`** — körs på alla triggers (PR och push):
1. Bygg image från `Dockerfile.hardened`
2. Trivy full rapport arkiveras som artefakt — alltid tillgänglig för granskning oavsett utfall
3. Trivy CRITICAL/HIGH-gate blockerar pipeline vid allvarliga fynd
4. SBOM genereras och arkiveras som artefakt
5. Image sparas och laddas upp som artefakt för nästa jobb

**`publish`** — körs bara vid push till `main` eller manuell trigger, kräver att `scan` godkänts:
1. Laddar exakt samma image som scannades — ingen rebuild, inget riskerar att digestet förändras
2. Push till GCR
3. Signering med Cosign → Rekor transparency log
4. Verifiering mot `cosign.pub` i repot

Detta ger ett flöde där en sårbar eller osignerad image aldrig kan nå klustret utan att blockeras automatiskt. Designen följer samma mönster som Lab 1:s Terraform-pipeline — tydlig jobseparation, artefakter för granskning, och secrets hanterade via GitHub utan att nycklarna exponeras i loggar eller kod.

### GitHub Secrets och CI/CD-pipeline

Pipelinen i `.github/workflows/container-security.yml` implementerar hela flödet automatiskt. Cosign-nyckeln och GCR-autentiseringen hanteras via GitHub Secrets — samma princip som `GCP_SA_KEY` i Lab 1:

| Secret               | Innehåll                                 | Användning i pipeline                                                |
|----------------------|------------------------------------------|----------------------------------------------------------------------|
| `COSIGN_PRIVATE_KEY` | Innehållet i `cosign.key` (base64-kodat) | Avkodas till temporär fil, signering körs, filen raderas direkt      |
| `COSIGN_PASSWORD`    | Lösenordet till privatnyckeln            | Injiceras som miljövariabel vid `cosign sign` — syns aldrig i loggar |
| `GCP_SA_KEY`         | Service account-nyckel (JSON)            | Autentisering mot GCR för `docker push`                              |

`cosign.pub` (publik nyckel) är committad till repot och används direkt vid verifiering — publika nycklar är avsedda att delas och utgör den auktoritativa verifieringsreferensen för projektet.

Det innebär att privatnyckeln aldrig behöver finnas på en utvecklarmaskin. Komprometteras en dator finns inga credentials att komma åt — exakt samma säkerhetsmotivering som för `GCP_SA_KEY` i Lab 1.

---

## Lärdomar från implementationen

### Lösenord och specialtecken i CI/CD
Under implementationen av Cosign-signeringen misslyckades pipeline-steget upprepade gånger med `decrypt: decryption failed` trots att lösenordet verifierades fungera lokalt. Orsaken visade sig vara att det ursprungliga lösenordet innehöll specialtecken som tolkades olika beroende på context — PowerShell lokalt, bash i GitHub Actions, och GitHub Secrets lagringsformat.

**Lärdomen:** Starka lösenord med specialtecken är rätt princip i de flesta sammanhang, men i CI/CD-pipelines där ett lösenord passeras genom flera lager (secret store → YAML → shell → verktyg) kan specialtecken orsaka svårspårade fel. För maskin-till-maskin-credentials i pipelines bör lösenord bestå av enbart bokstäver och siffror — entropin kan istället ökas genom längd. Ett 20-tecken långt alfanumeriskt lösenord är i praktiken starkare än ett 12-tecken lösenord med specialtecken, och undviker kompatibilitetsproblem helt.

### Taggar vs digest vid signering
Cosign varnade vid signering mot en tagg i stället för ett digest. En tagg är ett föränderligt pekare — den kan när som helst pekas om till en annan image. Att signera mot en tagg innebär därför att signaturen inte är garanterat kopplad till exakt det image-innehåll som verifieras vid ett senare tillfälle. Pipelinen uppdaterades att alltid hämta och använda digest-referensen (`sha256:...`) direkt efter push, vilket gör signaturen obrytbart bunden till rätt image-innehåll.
