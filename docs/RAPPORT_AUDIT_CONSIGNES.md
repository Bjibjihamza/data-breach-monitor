# Audit — Rapport vs Consignes vs Implémentation

**Projet :** Data Breach & Threat Intelligence Monitoring Platform  
**Date de l’audit :** 20 mai 2026  
**Documents analysés :**
- Consignes officielles : [`consgines.md`](../consgines.md) *(nom de fichier dans le dépôt ; équivalent attendu `consignes.md`)*
- Rapport écrit : [`report/rapport_data_breach_monitor.tex`](../report/rapport_data_breach_monitor.tex) / PDF compilé
- Code et documentation : `README.md`, `docs/SCOPE.md`, `docs/PROJECT_AUDIT.md`, backend `app/`, frontend `frontend/`, `docker-compose.yml`, `threat-intelligence-pipeline/`

**Périmètre :** analyse en lecture seule — aucune modification du rapport ou du code n’a été effectuée pour produire cet audit.

---

## 1. Synthèse exécutive

Le rapport actuel est **solide sur le plan technique descriptif** (sources OSINT, pipeline de traitement, politique de détection, captures d’écran des modules GitHub / Telegram / Google Alerts et du module Power BI CVE). Il correspond bien à une **documentation produit / architecture** du système réel.

En revanche, il **ne couvre pas la structure académique et professionnelle exigée** par les consignes M244 (Veille Technologique) : pas de problématique formalisée, pas de veille documentaire bibliographique, pas de planification (Gantt), pas de cahier des charges « client », pas de chapitre tests/validation, pas d’analyse critique structurée, pas de bibliographie, et une **introduction académique dédiée absente** (seul un résumé existe).

Par rapport à l’**implémentation réelle**, le rapport est **en retard** sur plusieurs briques importantes déjà livrées : dashboard React multi-pages (correlations, intelligence, live scan, latest scan, diagnostics…), APIs analytics et scan status, alerting Telegram/email, modes de scan backfill/incrémental, module de scoring GitHub avancé, entropie/validateurs, Kibana, et la documentation interne (`PROJECT_AUDIT.md`) qui décrit des limites connues non mentionnées dans le rapport.

| Dimension | Évaluation globale |
|-----------|-------------------|
| Alignement consignes M244 | **Faible à partiel** (~40 % des exigences couvertes) |
| Fidélité au code actuel | **Partiel** (~55 % des fonctionnalités majeures décrites) |
| Qualité rédactionnelle / visuelle | **Bonne** (mise en page, figures, exemples concrets) |
| Dimension portfolio / client | **Manquante** |
| Préparation soutenance orale (25+5 min) | **Non préparée dans le document** |

---

## 2. Exigences extraites de `consgines.md`

### 2.1 Objectif général du module
- Présentation professionnelle, analyse critique, résultats structurés, défense devant jury.

### 2.2 Structure obligatoire du rapport (13 sections)
1. Présentation du sujet (contexte, importance, *pourquoi / problème / impact*)
2. Problématique (claire, précise, lien monde professionnel)
3. Objectifs (principal + secondaires + résultats attendus)
4. Veille et recherche documentaire (sources fiables, récentes, variées, crédibilité)
5. Méthodologie de recherche (démarche, outils, logiciels)
6. Planification (tâches, calendrier, **Gantt recommandé**, équipe)
7. Présentation de la solution (description, fonctionnement, architecture, valeur ajoutée ↔ problématique)
8. Réalisation technique (développement, technologies, **captures d’écran**)
9. Démonstration (cas d’usage, démo préparée)
10. Tests et validation (méthodes, résultats, limites, tableaux/graphiques)
11. Analyse critique (forces, faiblesses, difficultés)
12. Recommandations (améliorations techniques et organisationnelles, perspectives)
13. Bibliographie (citations cohérentes et complètes)

### 2.3 Dimension professionnelle
- Rapport = **portfolio** pour convaincre un client.
- **Cahier des charges** : besoins client, objectifs, fonctionnalités, contraintes techniques, délais, ressources, résultats attendus.

### 2.4 Contraintes formelles
- Style professionnel, **introduction** et **conclusion** obligatoires, visuels, normes académiques, originalité (similarité ≤ 15 %).

### 2.5 Présentation orale
- 25 min + 5 min questions, tous les membres interviennent, pas de lecture, maîtrise du sujet, tenue professionnelle.

---

## 3. Structure actuelle du rapport (`.tex`)

| Élément | Présent dans le rapport |
|---------|-------------------------|
| Page de garde professionnelle | Oui |
| Résumé | Oui |
| Introduction (chapitre dédié) | **Non** |
| Ch. 1 — Contexte, objectifs, périmètre | Oui (partiellement couvre §1 et §3 des consignes) |
| Ch. 2 — Architecture et méthodologie de veille | Oui (orienté technique, pas recherche académique) |
| Ch. 3 — Sources et collecte (+ Power BI) | Oui (couvre §7–§8 partiellement) |
| Ch. 4 — Traitement, détection, classification | Oui |
| Conclusion générale | Oui |
| Bibliographie | **Non** |
| Annexes (Gantt, cahier des charges, tests) | **Non** |

**Figures réelles présentes :** diagramme conceptuel, overview, GitHub, Telegram, Google Alerts, collection runs, pipeline TIP, 3 pages Power BI.  
**Placeholder `\screenshotplaceholder` défini mais non utilisé** dans le corps final — les captures principales sont déjà intégrées pour 3 sources + BI.

---

## 4. Tableau — Consignes vs rapport

| Exigence (`consgines.md`) | Statut dans le rapport | Problème | Correction recommandée |
|---------------------------|------------------------|----------|-------------------------|
| 1. Présentation du sujet | Partiellement couvert | Contexte et périmètre OK ; manque l’argument « pourquoi ce sujet », impact métier chiffré, enjeux réglementaires (RGPD, NIS2, etc.) | Ajouter §1.1 « Enjeux » + statistiques/références secteur ; lier au besoin SOC |
| 2. Problématique | **Manquant** | Pas de question de recherche ni formulation « besoin client / difficultés observées » | Chapitre dédié : une problématique en une phrase + 3–5 constats terrain |
| 3. Objectifs | Partiellement couvert | Objectif global présent ; **objectifs secondaires non listés** ; livrables mesurables absents | Tableau objectifs principal / secondaires / indicateurs de succès |
| 4. Veille documentaire | **Manquant** | Aucune revue d’articles, normes, rapports (Verizon DBIR, ENISA, papers OSINT) | Chapitre veille : ≥8 sources variées (scientifique, pro, technique) avec analyse critique |
| 5. Méthodologie de recherche | Faible | « Méthodologie de veille » = pipeline technique, pas méthode de projet/R&D | Distinguer méthodo **projet** (agile, prototypage, tests) vs méthodo **collecte OSINT** |
| 6. Planification / Gantt | **Manquant** | Pas de calendrier, répartition équipe (4 membres cités page de garde seulement) | Annexe Gantt + tableau RACI par membre |
| 7. Présentation solution | Couvert | Architecture et valeur ajoutée bien décrites ; lien explicite problématique → solution faible faute de §2 | Reprendre problématique en intro du ch. solution |
| 8. Réalisation technique | Partiellement couvert | Stack incomplet (pas FastAPI/Celery/Redis/React/Kibana nommés clairement) ; pas de schéma déploiement Docker | § stack + diagramme déploiement + arborescence `app/` et `frontend/` |
| 9. Démonstration | Partiellement couvert | Captures = preuve visuelle ; pas de scénario démo pas-à-pas ni script soutenance | § « Scénario de démo » : scan manuel → détection → revue analyste → alerte |
| 10. Tests et validation | **Manquant** | Aucun protocole de test, métrique, jeu de données, limites quantifiées | Chapitre tests : unitaires, scans réels, taux FP, perf ; graphiques |
| 11. Analyse critique | **Manquant** | Quelques limites techniques (volumétrie, FP) sans bilan forces/faiblesses équipe | SWOT ou tableau forces/faiblesses/difficultés (s’appuyer sur `PROJECT_AUDIT.md`) |
| 12. Recommandations | Faible | Une phrase en conclusion seulement | Chapitre ou § structuré : court/moyen/long terme (tech + orga) |
| 13. Bibliographie | **Manquant** | Aucune citation formatée | Bibliographie IEEE/APA ; citer NVD, GitHub API, Telethon, papers Telegram OSINT du pipeline TIP |
| Portfolio / cahier des charges | **Manquant** | Ton « produit » mais pas document contractuel client | Annexe CDC : besoins SOC, fonctionnalités, contraintes, délais, ressources |
| Introduction académique | **Manquant** | Résumé ≠ introduction (plan, annonce des chapitres) | Chapitre Introduction avant le résumé ou après |
| Conclusion | Couvert | Correcte mais sans bilan objectifs atteints / non atteints | Conclure sur objectifs + ouverture professionnelle |
| Visuels professionnels | Couvert | Bon niveau ; légende Google Alerts avec faute (« image sur l(interface ») | Corriger typos légendes ; ajouter figures manquantes (voir §6) |
| Présentation orale | N/A écrit | Non adressée | Guide oral séparé : répartition 25 min, démo backup, Q&R anticipées |

---

## 5. Implémentation réelle — Vue d’ensemble

### 5.1 Architecture backend
- **FastAPI** (`app/main.py`) : health, scans, debug config, admin backfill, dashboard SPA.
- **Celery + Celery Beat + Redis** : tâches planifiées et scans manuels (`app/tasks.py`).
- **Elasticsearch** : index `breach_signals`, `collection_runs`, `collection_state`.
- **Kibana** (port 5601) : visualisation ES — **non mentionné dans le rapport**.
- **Collecteurs** : `github_collector`, `google_alerts_collector`, `telegram_collector`, `mock_paste_collector`.
- **Pipeline** : `detector.py`, `normalizer`, `redactor`, `deduplicator`, `scorer`, modules `app/detection/*` (policy, validators, entropy, extractors, noise, `github_scoring`).
- **Alerting** : `app/alerts/telegram_alert.py`, `email_alert.py` — high severity après indexation.
- **Modes de scan** : `backfill` vs `incremental` (`scan_modes.py`) ; backfill initial au démarrage Docker.
- **SQLite** : `config.sqlite3` pour état config — non documenté dans le rapport.

### 5.2 APIs principales (écart rapport)
Endpoints présents dans le code mais absents ou peu détaillés dans le rapport :

| Endpoint | Rôle |
|----------|------|
| `POST /scan/all`, `GET /scan/status`, `GET /scan/status/{source}` | Orchestration et suivi temps réel |
| `GET /analytics/correlations` | Regroupements cross-sources |
| `GET /analytics/intelligence-summary` | Synthèse analyste déterministe |
| `GET /analytics/source-diagnostics` | Diagnostic par requête/feed/canal |
| `GET /analytics/latest-scan`, `.../detections` | Focus dernier scan |
| `PATCH /detections/{hash}/status` | Workflow analyste |
| `GET/POST /admin/initial-backfill` | Premier remplissage historique |
| `GET /analytics/local-data-export` | Export local |

### 5.3 Frontend React (`frontend/`)
Routes actuelles (`App.jsx`) :

| Route | Mention rapport ? |
|-------|-------------------|
| `/dashboard` — Overview | Partiel (overview.png) |
| `/dashboard/detections` | Non nommé |
| `/dashboard/correlations` | **Non** |
| `/dashboard/intelligence` | **Non** |
| `/dashboard/latest-scan` | **Non** |
| `/dashboard/live-scan-status` | **Non** |
| `/dashboard/github` | Oui (captures) |
| `/dashboard/google-alerts` | Oui |
| `/dashboard/telegram` | Oui |
| `/dashboard/runs` | Partiel (collection.png) |
| `/dashboard/state` | **Non** |
| `/dashboard/diagnostics` | **Non** |
| `/dashboard/settings` | **Non** |

### 5.4 Module BI Threat Intelligence
- Sous-projet séparé : `threat-intelligence-pipeline/` (NVD batch, scrape Telegram/CVEFeed, PostgreSQL, Bronze/Silver/Gold, Power BI).
- Le rapport le décrit correctement au niveau conceptuel ; le lien avec la plateforme FastAPI (deux produits dans un même repo) pourrait être clarifié.

### 5.5 Tests
- `tests/test_core.py` référencé dans le README mais **répertoire tests vide ou absent** au moment de l’audit ; **aucun chapitre tests** dans le rapport — double écart.

### 5.6 Écarts factuels rapport ↔ config
| Point rapport | Réalité observée |
|---------------|------------------|
| « 16 alertes » Google Alerts | `PROJECT_AUDIT.md` indique **18 flux RSS valides** dans la config active |
| Table classification : `mock_paste` | Source démo/dev ; peu expliquée dans le corps du rapport |
| Dashboard = panneaux GitHub/Telegram/GA | Dashboard **11+ pages** React, pas seulement 3 vues sources |
| CVE comme « 4e source » de la plateforme principale | CVE analytique = **pipeline BI séparé** ; pas un collecteur Celery du core |

---

## 6. Tableau — Fonctionnalités implémentées vs rapport

| Fonctionnalité implémentée | Mentionnée dans le rapport ? | Importance | Section recommandée du rapport |
|----------------------------|-------------------------------|------------|--------------------------------|
| Docker Compose (api, worker, beat, redis, ES, kibana, frontend) | Non | Haute | Réalisation technique + annexe déploiement |
| Celery Beat (intervalles configurables) | Partiel (« planificateur ») | Haute | Architecture + config `.env` |
| FastAPI + liste endpoints REST | Non | Haute | Réalisation technique |
| Dashboard React Vite multi-pages | Partiel (3 sources) | Haute | Démonstration + captures par route |
| Live Scan Status + `/scan/status` | Non | Haute | Démonstration / observabilité |
| Latest Scan + détections du dernier scan | Non | Moyenne | Ch. traitement / dashboard |
| Correlations cross-sources | Non | Haute | Solution + valeur ajoutée analyste |
| Intelligence summary (actions recommandées) | Non | Haute | Solution / démo |
| Source diagnostics (par requête/feed) | Non | Moyenne | Tests & validation / limites |
| Collection runs & collection state | Partiel | Haute | Déjà amorcé — compléter métriques |
| Workflow revue analyste (PATCH status) | Non | Haute | Fonctionnalités + démo |
| Alerting Telegram bot + email SMTP | Non | Haute | Solution + contraintes éthiques |
| Modes scan `backfill` / `incremental` | Non | Moyenne | Méthodologie collecte |
| Initial backfill au démarrage | Non | Moyenne | Réalisation technique |
| `detection_policy.yml` + validateurs + entropie | Partiel (policy) | Haute | Ch.4 — détailler validateurs/entropy |
| `github_scoring.py` (scoring GitHub dédié) | Non | Moyenne | Détection et classification |
| `global_risks.yml` v2 (~116 requêtes, 20/run) | Partiel | Haute | GitHub + **limites connues** |
| Watchlists organisations (optionnel) | Non | Moyenne | Périmètre / extension |
| Kibana | Non | Moyenne | Stack technique |
| `mock_paste` (démo dev) | Tableau seulement | Faible | Périmètre test / hors prod |
| Menace pipeline TIP (PostgreSQL, NVD, Power BI) | Oui | Haute | Conserver — préciser séparation repo |
| Limites : relecture mêmes items, 20 requêtes GitHub fixes | Non | **Haute** | Analyse critique (cf. `PROJECT_AUDIT.md`) |
| Absence de tests automatisés exploitables | Non | Haute | Tests & validation (honnêteté académique) |

---

## 7. Points forts du rapport (à préserver)

1. **Identité visuelle professionnelle** (page de garde, typographie, figures intégrées).
2. **Positionnement défensif OSINT** clair et conforme au périmètre réel du code (`SCOPE.md`).
3. **Description du pipeline** collecte → normalisation → policy → redaction → stockage cohérente avec l’implémentation.
4. **Exemples concrets** (exposition GitHub critique, signal Telegram Avito.ma) — très utiles pour la soutenance.
5. **Module Power BI CVE** bien documenté avec 3 pages et captures.
6. **Tableaux de configuration** (`global_risks`, Telegram, Google Alerts, detection policy).
7. **Public cible** (SOC, RSSI, enseignement) pertinent pour la dimension portfolio.

---

## 8. Faiblesses et risques (liste structurée)

### 8.1 Conformité académique (M244)
- Absence de **problématique** et de **veille bibliographique** : critères souvent éliminatoires en jury.
- Pas de **Gantt** ni traçabilité du travail d’équipe sur 4 membres.
- Pas de **tests/validation** documentés alors que la consigne exige tableaux, graphiques et limites.
- Pas de **bibliographie** → risque sur l’originalité et la crédibilité des affirmations.
- **Introduction** formelle absente ; seul le résumé joue ce rôle partiellement.

### 8.2 Dimension professionnelle / portfolio
- Pas de **cahier des charges** « client SOC / RSSI ».
- Pas de proposition commerciale (délais, budget, SLA, livrables).
- Le rapport lit comme une **documentation technique interne**, pas comme une réponse à appel d’offres.

### 8.3 Alignement avec le produit réel
- **Sous-documentation** du dashboard React et des APIs récentes (correlations, intelligence, live scan).
- **Sur-représentation relative** du module Power BI par rapport au cœur FastAPI/Celery (équilibre chapitres à revoir selon ce que le jury notera).
- **Limites opérationnelles** connues (dédup, fenêtre GitHub 20 requêtes, stabilité RSS) non discutées — risque de questions embarrassantes en soutenance si la démo montre « 292 total inchangé ».
- Incohérence mineure **16 vs 18 alertes** Google Alerts.

### 8.4 Qualité rédactionnelle
- Fautes / légendes approximatives (ex. figure Google Alerts).
- Pas de chapitre **démonstration** avec script pas-à-pas et plan B (Docker, token GitHub, session Telethon).
- Références à `mock_paste` dans un tableau sans contexte pédagogique.

### 8.5 Soutenance orale (25+5 min)
- Le document ne prépare pas : répartition du temps, rôles par membre, questions anticipées, démo sans lecture.
- Aucune matrice « qui parle de quoi » pour respecter la participation de **tous** les membres.

---

## 9. Plan de mise à jour recommandé (ordre de priorité)

### Priorité 1 — Bloquant jury
1. Rédiger **Introduction** + **Problématique** + **Objectifs secondaires**.
2. Ajouter chapitre **Veille documentaire** + **Bibliographie** (≥15 références).
3. Ajouter **Planification** (Gantt + répartition équipe).
4. Ajouter **Tests et validation** (même si tests auto limités : tests manuels, scans, métriques ES).
5. Ajouter **Analyse critique** + **Recommandations** (s’inspirer de `docs/PROJECT_AUDIT.md`).

### Priorité 2 — Alignement produit
6. Chapitre **Stack technique** : FastAPI, Celery, Redis, ES, Kibana, React, Docker.
7. Section **Dashboard analyste** : toutes les routes + 2–3 captures par page clé (correlations, intelligence, live scan).
8. Documenter **workflow analyste**, **alerting**, **scan status**, modes backfill/incrémental.
9. Corriger chiffres (alertes RSS) et clarifier **séparation** plateforme monitoring vs pipeline BI CVE.

### Priorité 3 — Portfolio & soutenance
10. Annexe **Cahier des charges** client fictif ou partenaire universitaire.
11. Annexe **Scénario de démo** + checklist technique pré-soutenance.
12. Guide **oral 25 min** (4 intervenants × ~6 min).

---

## 10. Matrice de couverture rapide (consignes → chapitres rapport actuels)

| # Consigne | Chapitre(s) rapport actuel | Couverture estimée |
|------------|---------------------------|-------------------|
| 1 | Ch.1 §1.1 | 60 % |
| 2 | — | 0 % |
| 3 | Ch.1 §1.2–1.3 | 50 % |
| 4 | — | 0 % |
| 5 | Ch.2, Ch.4 §4.1 | 40 % (technique, pas académique) |
| 6 | — | 0 % |
| 7 | Ch.2–3 | 75 % |
| 8 | Ch.3–4 + figures | 65 % |
| 9 | Figures implicites | 40 % |
| 10 | — | 5 % |
| 11 | — | 10 % |
| 12 | Conclusion (1 phrase) | 15 % |
| 13 | — | 0 % |
| Portfolio / CDC | — | 0 % |

**Score global estimé : ~35–40 %** des exigences formelles M244 pleinement satisfaites.

---

## 11. Fichiers utiles pour la prochaine rédaction

| Fichier | Usage pour compléter le rapport |
|---------|----------------------------------|
| [`consgines.md`](../consgines.md) | Checklist officielle |
| [`README.md`](../README.md) | Stack, endpoints, dashboard routes |
| [`docs/SCOPE.md`](SCOPE.md) | Périmètre défensif / hors scope |
| [`docs/PROJECT_AUDIT.md`](PROJECT_AUDIT.md) | Limites, métriques, analyse critique factuelle |
| [`docker-compose.yml`](../docker-compose.yml) | Schéma déploiement |
| [`report/rapport_data_breach_monitor.tex`](../report/rapport_data_breach_monitor.tex) | Source LaTeX à étendre |
| [`threat-intelligence-pipeline/README.md`](../threat-intelligence-pipeline/README.md) | Détail module BI + référence arXiv |

---

## 12. Conclusion de l’audit

Le rapport est **techniquement crédible** et **visuellement au niveau professionnel** pour décrire le cœur métier (OSINT multi-sources + détection + BI CVE). Il n’est **pas encore un rapport de Veille Technologique M244 complet** ni un **portfolio client** au sens des consignes.

La priorité n’est pas de réécrire les chapitres 2–4 (déjà bons), mais d’**ajouter les couches manquantes** : problématique, veille, planification, tests, critique, bibliographie, CDC, et de **synchroniser** le texte avec l’état réel du dépôt (dashboard React étendu, APIs, alerting, limites documentées dans `PROJECT_AUDIT.md`).

---

*Document généré par audit automatisé du dépôt — à valider par l’équipe projet avant toute soumission.*
