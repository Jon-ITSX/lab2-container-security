# Reflektion – Lab 2 (Container Security)

I den här labben blev det tydligt hur stor skillnad valet av base image och beroenden gör för säkerhetsläget.
Baseline-imagen gav många sårbarheter direkt, både i OS-paket och i Python-bibliotek, vilket gjorde riskbilden konkret och ganska omfattande.
När imagen härdades med nyare beroenden, non-root-användare, slim-baserad runtime och multi-stage build minskade antalet allvarliga findings tydligt — HIGH minskade från 37 till 2 och CRITICAL från 5 till 2 totalt.
Multi-stage build visade sig vara ett kraftfullt verktyg: genom att hålla pip och build-verktyg i ett separat builder-steg når de aldrig slutbilden och kan inte utnyttjas vid en eventuell kompromiss.

Jag lärde mig också att säkerhet inte bara handlar om kod, utan om hela leveranskedjan runt containern.
SBOM är viktig eftersom den ger spårbarhet. Man ser exakt vilka komponenter som finns i image och kan följa upp nya CVE:er snabbare utan att behöva inspektera image manuellt.
Gatekeeper ändrar arbetssättet i Kubernetes genom att flytta säkerhetskrav till policynivå, så fel blockeras redan vid deployment — ingen manuell granskning av manifests behövs.
Cosign-signeringen med Rekor transparency log lägger till ett externt, oavvisbart kvitto på att imagen är äkta och oförändrad, vilket är grunden för supply chain-integritet.
CI/CD-pipelinen knyter ihop allt: scanning, SBOM-generering, signering och push automatiseras i en jobbkedja där en osignerad eller sårbar image aldrig kan nå klustret — samma shift-left-princip och secrets-hantering via GitHub Secrets som etablerades i Lab 1 med Terraform-pipelinen.

En praktisk lärdom från implementationen är att kvarvarande CVEs inte alltid är åtgärdbara — flera CRITICAL och HIGH i OS-paketen saknar fix i nuläget. Det rätta svaret är inte att ignorera dem tyst utan att dokumentera beslutet och konfigurera pipelinen att skilja på fixbara och ofixbara fynd med `--ignore-unfixed`. Det är en viktig insikt: säkerhetsarbete handlar lika mycket om att hantera restrisker transparent som att eliminera dem.

Skillnaden mellan lokalt fungerande lösningar och CI-miljön visade sig också vara en konkret lärdom. Lösenord med specialtecken fungerade felfritt lokalt men orsakade `decryption failed` i GitHub Actions eftersom tecknen tolkades olika i olika kontexter. På samma sätt fungerar inte alla auth-metoder mot GCP i CI-miljö trots att de verkar likvärdiga — `docker/login-action` med `_json_key` gav permissions-fel medan `google-github-actions/auth` fungerade. Lokal testning är med andra ord nödvändig men inte tillräcklig.

När cosign signerade mot en tagg i stället för ett digest kom en varning om att taggar kan pekas om till en annan image — signaturen skulle då gälla fel image utan att någon märker det. Att byta till digest-baserad signering var ett litet steg men ett principiellt viktigt: verktyg kan aktivt guida säkerhetsbeslut om man läser och agerar på deras varningar.
