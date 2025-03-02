# /home/mute4368/backend/passenger_wsgi.py
import os
import sys

# Ajouter le répertoire courant au chemin Python
INTERP = "/home/mute4368/virtualenv/backend/3.12/bin/python"
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Ajouter le répertoire de l'application au chemin Python
sys.path.insert(0, os.path.dirname(__file__))

# Importer l'application FastAPI et la configurer pour WSGI
from main import app
from fastapi.middleware.wsgi import WSGIMiddleware

# Cette partie est cruciale - elle rend votre application FastAPI compatible avec WSGI
# que Passenger utilise
application = WSGIMiddleware(app)