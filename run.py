"""Point d'entrée : lance le serveur de développement (`python run.py`).

En production (PythonAnywhere), le fichier WSGI importe simplement `app` depuis ce module :
    from run import app as application
"""
import socket

from src import create_app
from src.config import IS_DEV

# Instance de l'application : c'est aussi l'objet que Flask (`flask run`) et le serveur WSGI vont chercher.
app = create_app()


def local_ip():
    """Adresse du PC sur le réseau local (pour ouvrir le site depuis un téléphone sur le même Wi-Fi)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # ne transmet rien, sert juste à déterminer l'IP locale
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Ne se lance que si on exécute `python run.py` directement (pas à l'import par le serveur WSGI).
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print(" CruxWall — accessible sur ce PC : http://127.0.0.1:5000")
    print(" CruxWall — accessible depuis un autre appareil du même")
    print(f" réseau Wi-Fi (tablette, téléphone) : http://{local_ip()}:5000")
    print("=" * 60 + "\n")
    if IS_DEV:
        # host="0.0.0.0" : joignable depuis les autres appareils du réseau Wi-Fi.
        # use_debugger=False : rechargement automatique, mais PAS le débogueur interactif de Werkzeug, qui
        # permet d'exécuter du code Python depuis le navigateur — dangereux sur un réseau partagé.
        app.run(host="0.0.0.0", port=5000, debug=True, use_debugger=False)
    else:
        print("Mode production (CRUXWALL_ENV non défini) : écoute locale uniquement.")
        print("Pour travailler en local depuis une tablette/téléphone, ajoute CRUXWALL_ENV=development dans .env")
        app.run(host="127.0.0.1", port=5000, debug=False)
