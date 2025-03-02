import os
import sys

# Assurer que le répertoire courant est dans le chemin Python
sys.path.insert(0, os.path.dirname(__file__))

# Variable de débogage simple pour afficher les erreurs
def debug_application(environ, start_response):
    status = '200 OK'
    output = b'Mode debug - Test de connexion'
    response_headers = [('Content-type', 'text/plain'),
                       ('Content-Length', str(len(output)))]
    start_response(status, response_headers)
    return [output]

# Essayer d'importer l'application avec gestion d'erreur
try:
    # Import direct de l'application depuis main.py
    from main import app
    
    # Utiliser un adaptateur WSGI standard pour FastAPI
    import uvicorn.middleware.wsgi
    application = uvicorn.middleware.wsgi.WSGIMiddleware(app)
    
except Exception as e:
    import traceback
    error_msg = f"Erreur: {str(e)}\n\n{traceback.format_exc()}"
    
    # Définir une application de secours qui affiche l'erreur
    def application(environ, start_response):
        status = '200 OK'  # Utiliser 200 pour que le contenu s'affiche
        output = error_msg.encode('utf-8')
        response_headers = [('Content-type', 'text/plain'),
                           ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]