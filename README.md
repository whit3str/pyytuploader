PyYTUploader
============

PyYTUploader est un outil automatisé pour télécharger des vidéos sur YouTube depuis un dossier local. Il est particulièrement utile pour les créateurs de contenu qui souhaitent automatiser leur processus de publication.

Fonctionnalités
---------------

*   Téléchargement automatique de vidéos vers YouTube
    
*   Surveillance périodique d'un dossier pour détecter de nouvelles vidéos
    
*   Support pour les métadonnées Ganymede (pour les VODs Twitch)
    
*   Création automatique de playlists par chaîne
    
*   Notifications Discord pour les téléchargements réussis
    
*   Reprise des téléchargements interrompus
    
*   Gestion des miniatures
    

Installation
------------

Prérequis
---------

*   Python 3.7 ou supérieur
    
*   Un compte Google avec accès à l'API YouTube
    

Installation avec Docker (recommandée)
--------------------------------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   bashdocker pull ghcr.io/whit3str/pyytuploader:dev   `

Configuration Docker
--------------------

Créez un fichier docker-compose.yml :

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   textversion: '3'  services:    pyytuploader:      image: ghcr.io/whit3str/pyytuploader:dev      container_name: youtube-uploader      volumes:        - /chemin/vers/config:/app/data  # Pour la configuration, les tokens et l'historique        - /chemin/vers/videos:/app/videos  # Montez votre répertoire de vidéos ici      restart: unless-stopped      environment:        - TZ=Europe/Paris  # Définissez votre fuseau horaire ici        - YTU_VIDEOS_FOLDER=/app/videos        - YTU_PRIVACY_STATUS=private  # Options: private, unlisted, public        - YTU_CHECK_INTERVAL=60  # Minutes entre les analyses de dossier        - YTU_DISCORD_WEBHOOK=https://discord.com/api/webhooks/votre-webhook        # Variables d'environnement optionnelles:        - YTU_VIDEO_CATEGORY=20        - YTU_DESCRIPTION=Téléchargé avec YTU Automated Uploader        - YTU_GANYMEDE_MODE=true        - YTU_TAGS=ganymede,vod        - YTU_AUTO_PLAYLIST=true   `

Configuration
-------------

Obtenir des identifiants OAuth
------------------------------

1.  Allez sur [Google Cloud Console](https://console.cloud.google.com/)
    
2.  Créez un nouveau projet
    
3.  Activez l'API YouTube Data v3
    
4.  Créez des identifiants OAuth 2.0
    
5.  Téléchargez le fichier JSON et placez-le dans le dossier /app/data/client\_secrets.json
    

Variables d'environnement
-------------------------

VariableDescriptionValeur par défautYTU\_VIDEOS\_FOLDERDossier contenant les vidéos à télécharger''YTU\_PRIVACY\_STATUSStatut de confidentialité des vidéos'private'YTU\_CHECK\_INTERVALIntervalle de vérification (minutes)60YTU\_CLIENT\_SECRETSChemin vers le fichier client\_secrets.json'data/client\_secrets.json'YTU\_VIDEO\_CATEGORYID de catégorie YouTube'22'YTU\_DESCRIPTIONDescription par défaut des vidéos'Uploaded with YTU'YTU\_TAGSTags séparés par des virgules'YTU Upload'YTU\_GANYMEDE\_MODEActiver le mode Ganymede pour les VODs'false'YTU\_AUTO\_PLAYLISTAjouter automatiquement aux playlists'false'YTU\_DISCORD\_WEBHOOKURL du webhook Discord pour les notifications''

Categories 

1	Film & Animation
2	Autos & Vehicles
10	Music
15	Pets & Animals
17	Sports
18	Short Movies
19	Travel & Events
20	Gaming
21	Videoblogging
22	People & Blogs
23	Comedy
24	Entertainment
25	News & Politics
26	Howto & Style
27	Education
28	Science & Technology
29	Nonprofits & Activism
30	Movies
31	Anime/Animation
32	Action/Adventure
33	Classics
34	Comedy
35	Documentary
36	Drama
37	Family
38	Foreign
39	Horror
40	Sci-Fi/Fantasy
41	Thriller
42	Shorts
43	Shows
44	Trailers

Utilisation
-----------

Première exécution
------------------

Lors de la première exécution, vous devrez autoriser l'application à accéder à votre compte YouTube :

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   bashdocker-compose up   `

Suivez les instructions pour l'authentification OAuth.

Mode Ganymede
-------------

Le mode Ganymede est conçu pour les VODs Twitch téléchargées avec [Ganymede](https://github.com/Zibbp/ganymede). Il extrait automatiquement les métadonnées des fichiers JSON associés.

Notifications Discord
---------------------

Pour recevoir des notifications sur Discord lorsqu'une vidéo est téléchargée avec succès :

1.  Créez un webhook dans votre serveur Discord
    
2.  Ajoutez l'URL du webhook dans la variable d'environnement YTU\_DISCORD\_WEBHOOK
    

Dépannage
---------

Les notifications Discord ne fonctionnent pas
---------------------------------------------

*   Vérifiez que l'URL du webhook est correcte
    
*   Assurez-vous que le webhook a les permissions nécessaires
    
*   Vérifiez les journaux Docker pour les erreurs
    

Problèmes d'authentification
----------------------------

Si vous rencontrez des problèmes d'authentification :

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   bashdocker-compose down  docker volume rm youtube-uploader_data  docker-compose up   `

Licence
-------

Ce projet est sous licence MIT.

Contributions
-------------

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.