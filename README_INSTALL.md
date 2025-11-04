# Guide d'installation - DCA Discord Bot pour CasaOS

## Étapes d'installation

1) Place tous les fichiers dans un dossier sur ton NAS/serveur (ex: /home/user/casa-dca-bot)

2) Edite `config.yaml` et renseigne `webhook_url` et `admin.admin_tokens`.

3) Crée le dossier data :
   ```bash
   mkdir -p data
   ```

4) Build & run via CasaOS custom app (ou terminal) :
   ```bash
   docker compose up -d --build
   ```

5) Consulter les logs :
   ```bash
   docker logs -f dca-entry-discord-bot
   ```

6) Tests : attends 22:10 UTC un jour ouvré ou modifie temporairement la cron dans le code pour exécuter immédiatement.

## Notes de sécurité

- Ne commit pas `config.yaml` dans un repo public.
- Rotate webhook si compromis.

## Configuration

- **Timezone** : Le bot utilise UTC par défaut. Les tâches s'exécutent à 22:10 UTC (après la clôture des marchés US).
- **Tickers** : Modifie la liste dans `config.yaml` pour surveiller d'autres ETF/actions.
- **Poids** : Ajuste les poids des différents indicateurs selon ta stratégie.

## Dépannage

- Si le container ne démarre pas, vérifie les permissions du fichier `config.yaml`.
- Si aucun message Discord n'est envoyé, vérifie que l'URL du webhook est correcte.
- Les logs sont disponibles dans `./data/bot_daily_score.log` et via `docker logs`.
