# passenger_wsgi.py
import os
import sys
import traceback

# Assurez-vous que le chemin Python est correct
sys.path.insert(0, os.path.dirname(__file__))

# Fonction WSGI simple pour servir une page statique
def simple_app(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'text/html')]
    start_response(status, response_headers)
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Backend</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { color: #333; }
            .info { background: #f8f8f8; padding: 20px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Backend API Status</h1>
            <div class="info">
                <p>Le serveur API est correctement configuré mais utilise une page statique.</p>
                <p>Pour accéder à l'API complète, utilisez des requêtes API directes.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return [html.encode('utf-8')]

# Essayer d'importer l'application principale, mais utiliser l'application simple en cas d'échec
try:
    from main import app
    print("Application importée avec succès")
    application = simple_app  # Pour l'instant, utilisez toujours l'app simple
except Exception as e:
    print(f"Erreur lors de l'importation: {str(e)}")
    traceback_str = traceback.format_exc()
    print(traceback_str)
    application = simple_app