import os
import sys
import subprocess
import signal
import time

# Chemin vers Python dans l'environnement virtuel
PYTHON_PATH = "/home/mute4368/virtualenv/backend/3.12/bin/python"

# Démarrer uvicorn comme un processus détaché
def start_uvicorn():
    cmd = [PYTHON_PATH, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
    process = subprocess.Popen(cmd, cwd=os.path.dirname(__file__))
    # Attendre que le serveur démarre
    time.sleep(2)
    return process

# Stopper uvicorn
def stop_uvicorn(process):
    if process:
        process.terminate()
        process.wait()

# Variable pour stocker le processus uvicorn
uvicorn_process = None

# Fonction WSGI pour transmettre les requêtes au serveur uvicorn
def application(environ, start_response):
    global uvicorn_process
    
    # Démarrer uvicorn si ce n'est pas déjà fait
    if not uvicorn_process:
        uvicorn_process = start_uvicorn()
    
    # Proxy simple vers uvicorn
    import requests
    
    # Construire l'URL à partir de la requête
    path = environ.get('PATH_INFO', '')
    query = environ.get('QUERY_STRING', '')
    url = f"http://127.0.0.1:8000{path}"
    if query:
        url += f"?{query}"
    
    method = environ.get('REQUEST_METHOD', 'GET')
    
    # Lire le corps de la requête si nécessaire
    content_length = environ.get('CONTENT_LENGTH', '')
    body = None
    if content_length:
        body = environ['wsgi.input'].read(int(content_length))
    
    # Collecter les en-têtes
    headers = {}
    for key, value in environ.items():
        if key.startswith('HTTP_'):
            header_name = key[5:].replace('_', '-').title()
            headers[header_name] = value
    
    # Effectuer la requête vers uvicorn
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=body,
            timeout=30
        )
        
        # Préparer la réponse WSGI
        start_response(f"{response.status_code} {response.reason}", 
                      [(name, value) for name, value in response.headers.items()])
        
        return [response.content]
    
    except Exception as e:
        # En cas d'erreur, renvoyer une page d'erreur
        status = '500 Internal Server Error'
        output = f"Erreur lors de la communication avec le serveur backend: {str(e)}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'),
                           ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]

# Gérer l'arrêt propre du serveur
def shutdown():
    global uvicorn_process
    if uvicorn_process:
        stop_uvicorn(uvicorn_process)

# Installer un gestionnaire de signal pour arrêter proprement le serveur
signal.signal(signal.SIGTERM, lambda signum, frame: shutdown())