"""Envoi d'emails HTML avec le logo SmartFactory intégré (inline CID).

Les images en data-URI (``data:image/png;base64,...``) sont bloquées ou
supprimées par la plupart des clients de messagerie (Gmail, Outlook, Yahoo...).
La méthode fiable consiste à joindre l'image à l'email en pièce "inline"
(``Content-Disposition: inline``) puis à la référencer dans le HTML via
``cid:``. On force l'enveloppe en ``multipart/related`` pour que les clients
résolvent correctement le ``cid:``.
"""
import base64
import os
from email.mime.image import MIMEImage

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

# Identifiant utilisé dans le HTML : <img src="cid:smartfactory-logo">
LOGO_CID = 'smartfactory-logo'
LOGO_FILENAME = 'logoSmart.png'


def get_logo_bytes():
    """Retourne les octets PNG du logo, ou ``None`` s'il est introuvable.

    On privilégie ``EMAIL_LOGO_B64`` (logo déjà redimensionné au démarrage)
    puis on retombe sur la lecture directe des fichiers connus.
    """
    b64 = getattr(settings, 'EMAIL_LOGO_B64', '')
    if b64:
        try:
            return base64.b64decode(b64)
        except (ValueError, TypeError):
            pass

    candidates = [
        os.path.join(settings.BASE_DIR, 'staticfiles', LOGO_FILENAME),
        os.path.join(
            settings.BASE_DIR.parent, 'Smartfactory-frontend',
            'src', 'assets', LOGO_FILENAME,
        ),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, 'rb') as fh:
                    return fh.read()
            except OSError:
                continue
    return None


def send_html_email(subject, text_body, html_body, to_email, fail_silently=False):
    """Envoie un email HTML avec le logo SmartFactory en pièce inline.

    Retourne le message construit (utile pour les tests).
    """
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    # multipart/related : indispensable pour l'affichage des images cid:.
    message.mixed_subtype = 'related'
    message.attach_alternative(html_body, 'text/html')

    logo_bytes = get_logo_bytes()
    if logo_bytes:
        image = MIMEImage(logo_bytes, _subtype='png')
        image.add_header('Content-ID', f'<{LOGO_CID}>')
        image.add_header('Content-Disposition', 'inline', filename=LOGO_FILENAME)
        message.attach(image)

    message.send(fail_silently=fail_silently)
    return message
