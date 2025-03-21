from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from fastapi import Form


router = APIRouter()

@router.post("/send-email")
async def send_email(
    to_email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    attachments: List[UploadFile] = File(None),
):
    try:
        # Configuration email
        sender_email = "support@app.tag-appore.com"
        smtp_password = "FyrJXhtT21A}"
        
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Ajouter le corps du message
        msg.attach(MIMEText(message, 'plain'))
        
        # Ajouter les pièces jointes
        if attachments:
            for attachment in attachments:
                content = await attachment.read()
                part = MIMEApplication(content, Name=attachment.filename)
                part['Content-Disposition'] = f'attachment; filename="{attachment.filename}"'
                msg.attach(part)
        
        # Envoyer l'email via O2switch
        with smtplib.SMTP_SSL('app.tag-appore.com', 465) as server:
            server.login(sender_email, smtp_password)
            server.send_message(msg)
            
        return {"message": "Email envoyé avec succès"}
    
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/send-credentials")
async def send_credentials(
    email: str = Form(...),
    companyName: str = Form(...),
    password: str = Form(...)
):
    try:
        # Configuration email
        sender_email = "support@app.tag-appore.com"
        smtp_password = "FyrJXhtT21A}"
        
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = email
        msg['Subject'] = f"Vos identifiants pour {companyName}"
        
        body = f"""
        Bienvenue chez Tag Appore Dashboard !
        
        Voici vos identifiants de connexion :
        Email : {email}
        Mot de passe : {password}
        
        Equipe Tag Appore.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP_SSL('app.tag-appore.com', 465) as server:
            server.login(sender_email, smtp_password)
            server.send_message(msg)
            
        return {"message": "Credentials sent successfully"}
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/send-password-reset")
async def send_password_reset(
    to_email: str = Form(...),
    new_password: str = Form(...)
):
    try:
        # Configuration email
        sender_email = "support@app.tag-appore.com"
        smtp_password = "FyrJXhtT21A}"
        
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = "Réinitialisation de votre mot de passe Tag Appore"
        
        body = f"""
        Bonjour,
        
        Votre mot de passe a été réinitialisé.
        Voici votre nouveau mot de passe : {new_password}
        
        Nous vous recommandons de le changer lors de votre prochaine connexion.
        
        Cordialement,
        L'équipe Tag Appore
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP_SSL('app.tag-appore.com', 465) as server:
            server.login(sender_email, smtp_password)
            server.send_message(msg)
            
        return {"message": "Email de réinitialisation envoyé avec succès"}
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))