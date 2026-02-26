# 📊 Pilotage des Demandes BI - Orange Money

Application Streamlit de gestion collaborative des demandes BI avec suivi en temps réel.

## Déploiement sur Streamlit Cloud

1. Créez un dépôt GitHub et poussez le contenu de ce dossier
2. Allez sur [share.streamlit.io](https://share.streamlit.io)
3. Connectez votre dépôt GitHub
4. Sélectionnez `app.py` comme fichier principal
5. Cliquez sur "Deploy"

## Déploiement local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure du projet

```
streamlit_app/
├── app.py                 # Application principale
├── requirements.txt       # Dépendances Python
├── packages.txt           # Dépendances système (vide)
├── README.md              # Documentation
├── .streamlit/
│   └── config.toml        # Configuration Streamlit
└── assets/
    └── logo.png           # Logo Orange Money
```

## Mot de passe administrateur

Le mot de passe admin par défaut est : `OMCMBI`