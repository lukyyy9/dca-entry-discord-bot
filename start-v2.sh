#!/bin/bash
# start-v2.sh - Script de démarrage rapide pour la V2

echo "🤖 Bot DCA - Démarrage V2"
echo "=========================="

# Vérifier que config.yaml existe
if [ ! -f "config.yaml" ]; then
    echo "❌ Erreur: config.yaml n'existe pas"
    echo "Veuillez créer un fichier config.yaml avec votre configuration"
    exit 1
fi

# Créer le répertoire data
mkdir -p data

# Arrêter les anciens conteneurs
echo "🛑 Arrêt des anciens conteneurs..."
docker-compose down

# Construire l'image
echo "🔨 Construction de l'image Docker..."
docker build -t imluky/dca-entry-discord-bot:v2 .

# Démarrer les services
echo "🚀 Démarrage des services..."
docker-compose up -d

echo ""
echo "✅ Services démarrés !"
echo ""
echo "📊 Bot DCA : docker logs -f dca-bot"
echo "🌐 Interface web : http://localhost:5001"
echo "   (Token d'admin configuré dans config.yaml)"
echo ""
echo "Commandes utiles:"
echo "  - Voir les logs du bot    : docker-compose logs -f dca-bot"
echo "  - Voir les logs du web    : docker-compose logs -f dca-web"
echo "  - Arrêter les services    : docker-compose down"
echo "  - Redémarrer              : docker-compose restart"
