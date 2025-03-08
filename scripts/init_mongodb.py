import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, TEXT

async def init_mongodb():
    # Connexion MongoDB
    client = AsyncIOMotorClient("mongodb+srv://tagappore:QMQNS2mWlaL3EQAX@cluster0.1uxvq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    db = client.dashboard_db
    
    print("Initialisation de la base de données MongoDB...")

    # Collection Users
    try:
        # Création des index pour la collection users
        user_indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("role", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)])
        ]
        await db.users.create_indexes(user_indexes)
        print("✓ Index de la collection users créés")
    except Exception as e:
        print(f"⨯ Erreur lors de la création des index users: {str(e)}")

    # Collection Schedules
    try:
        # Création des index pour la collection schedules
        schedule_indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("date", ASCENDING)]),
            IndexModel([("shift_type", ASCENDING)])
        ]
        await db.schedules.create_indexes(schedule_indexes)
        print("✓ Index de la collection schedules créés")
    except Exception as e:
        print(f"⨯ Erreur lors de la création des index schedules: {str(e)}")

    # Collection Logs
    try:
        # Création des index pour la collection logs
        log_indexes = [
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("action", ASCENDING)]),
            IndexModel([("timestamp", ASCENDING)]),
            IndexModel([("ip_address", ASCENDING)])
        ]
        await db.logs.create_indexes(log_indexes)
        print("✓ Index de la collection logs créés")
    except Exception as e:
        print(f"⨯ Erreur lors de la création des index logs: {str(e)}")

    print("\nStructure de la base de données :")
    print("""
    database: dashboard_db
    ├── collections:
    │   ├── users
    │   │   ├── _id: ObjectId
    │   │   ├── email: string (unique)
    │   │   ├── username: string (unique)
    │   │   ├── hashed_password: string
    │   │   ├── role: string (enum: super_admin, admin, agent, technician)
    │   │   ├── is_active: boolean
    │   │   ├── created_at: datetime
    │   │   └── updated_at: datetime
    │   │
    │   ├── schedules
    │   │   ├── _id: ObjectId
    │   │   ├── user_id: string (ref: users._id)
    │   │   ├── date: date
    │   │   ├── start_time: string
    │   │   ├── end_time: string
    │   │   ├── shift_type: string (enum: morning, afternoon, night)
    │   │   ├── notes: string
    │   │   ├── created_at: datetime
    │   │   └── updated_at: datetime
    │   │
    │   └── logs
    │       ├── _id: ObjectId
    │       ├── user_id: string (ref: users._id)
    │       ├── action: string
    │       ├── details: string
    │       ├── ip_address: string
    │       └── timestamp: datetime
    """)

    # Création des validations pour les collections
    await create_validations(db)

    print("\nInitialisation terminée!")
    client.close()

async def create_validations(db):
    try:
        # Validation pour la collection users
        await db.command({
            "collMod": "users",
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["email", "username", "hashed_password", "role", "is_active"],
                    "properties": {
                        "email": {
                            "bsonType": "string",
                            "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
                        },
                        "username": {
                            "bsonType": "string",
                            "minLength": 3
                        },
                        "role": {
                            "enum": ["super_admin", "admin", "agent", "technician"]
                        },
                        "is_active": {
                            "bsonType": "bool"
                        }
                    }
                }
            }
        })
        print("✓ Validation de la collection users configurée")

        # Validation pour la collection schedules
        await db.command({
            "collMod": "schedules",
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["user_id", "date", "start_time", "end_time", "shift_type"],
                    "properties": {
                        "shift_type": {
                            "enum": ["morning", "afternoon", "night"]
                        },
                        "start_time": {
                            "bsonType": "string",
                            "pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$"
                        },
                        "end_time": {
                            "bsonType": "string",
                            "pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$"
                        }
                    }
                }
            }
        })
        print("✓ Validation de la collection schedules configurée")

    except Exception as e:
        print(f"⨯ Erreur lors de la configuration des validations: {str(e)}")

if __name__ == "__main__":
    asyncio.run(init_mongodb())