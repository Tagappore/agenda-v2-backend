import asyncio
import sys
import os
from pymongo import MongoClient
from passlib.context import CryptContext
from datetime import datetime
from getpass import getpass

# Ajoutez le chemin du backend au PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_super_admin():
    # Connexion à la base de données
    client = MongoClient("mongodb+srv://tagappore:QMQNS2mWlaL3EQAX@cluster0.1uxvq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    db = client.dashboard_db
    
    print("\n=== Création/Réinitialisation du Super Admin ===\n")
    
    # Vérifier si un super admin existe déjà
    existing_super_admin = db.users.find_one({"role": "super_admin"})
    if existing_super_admin:
        confirm = input("Un super admin existe déjà. Voulez-vous le réinitialiser? (o/n): ")
        if confirm.lower() != 'o':
            print("Opération annulée.")
            return
        
        # Supprimer l'ancien super admin
        db.users.delete_one({"role": "super_admin"})
    
    # Collecter les informations du nouveau super admin
    print("\nEntrez les informations du super admin:")
    email = input("Email: ")
    username = input("Username: ")
    password = getpass("Mot de passe: ")
    confirm_password = getpass("Confirmez le mot de passe: ")
    
    if password != confirm_password:
        print("Les mots de passe ne correspondent pas!")
        return
    
    # Créer le nouveau super admin
    new_super_admin = {
        "email": email,
        "username": username,
        "hashed_password": pwd_context.hash(password),
        "role": UserRole.SUPER_ADMIN.value,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    try:
        result = db.users.insert_one(new_super_admin)
        print("\nSuper admin créé avec succès!")
        print(f"ID: {result.inserted_id}")
        print(f"Email: {email}")
        print(f"Username: {username}")
        print("\nVeuillez conserver ces informations en lieu sûr.")
        
    except Exception as e:
        print(f"\nErreur lors de la création du super admin: {str(e)}")
    
    finally:
        # Fermer la connexion à la base de données
        client.close()

if __name__ == "__main__":
    create_super_admin()