import os
import sys
import traceback

# Chemin Python
sys.path.insert(0, os.path.dirname(__file__))

# Journal d'erreurs
def log_error(message):
    with open('/home/mute4368/backend/error.log', 'a') as f:
        f.write(f"{message}\n")

# Charger les variables d'environnement
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                key, value = line.split('=', 1)
                os.environ[key] = value

# Créer une fonction WSGI basique qui redirige vers l'API
def create_wsgi_app():
    try:
        # Charger les variables d'environnement
        load_env()
        log_error("Variables d'environnement chargées")
        
        # WSGI handler pour FastAPI
        def wsgi_handler(environ, start_response):
            # Page d'accueil simple
            if environ['PATH_INFO'] == '/':
                status = '200 OK'
                output = b'API Backend is running!'
                headers = [('Content-type', 'text/plain'),
                          ('Content-Length', str(len(output)))]
                start_response(status, headers)
                return [output]
            
            # Redirection vers l'API
            elif environ['PATH_INFO'].startswith('/api'):
                # Importer uniquement quand nécessaire
                from main import app
                from fastapi.middleware.wsgi import WSGIMiddleware
                
                # Créer le bridge ASGI-WSGI
                api_app = WSGIMiddleware(app)
                return api_app(environ, start_response)
            
            # Autres chemins
            else:
                status = '404 Not Found'
                output = b'Not Found'
                headers = [('Content-type', 'text/plain'),
                          ('Content-Length', str(len(output)))]
                start_response(status, headers)
                return [output]
        
        return wsgi_handler
        
    except Exception as e:
        log_error(f"Erreur dans create_wsgi_app: {str(e)}")
        log_error(traceback.format_exc())
        
        # Application de fallback en cas d'erreur
        def error_app(environ, start_response):
            status = '500 Internal Server Error'
            output = f"Error: {str(e)}".encode('utf-8')
            headers = [('Content-type', 'text/plain'),
                      ('Content-Length', str(len(output)))]
            start_response(status, headers)
            return [output]
        
        return error_app

# Créer l'application WSGI
application = create_wsgi_app()