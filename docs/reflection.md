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
