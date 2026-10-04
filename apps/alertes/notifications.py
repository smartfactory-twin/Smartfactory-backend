"""Module 8 — Abstraction des canaux de notification (UC-28).

`NotificationService` isole l'alerte du *comment* on prévient :

    notify_in_app()  → toujours disponible, sans dépendance externe
    notify_email()   → activable/désactivable par la configuration
    notify_sms()     → Twilio OPTIONNEL, architectural uniquement

Contraintes tenues par ce module :

* `dispatch()` **ne lève jamais** : une alerte est créée quoi qu'il arrive,
  et un canal en échec n'empêche pas les autres ;
* aucun identifiant SMTP en dur, tout vient de `settings` / environnement ;
* sans configuration email, on journalise clairement et on continue ;
* le filtrage des destinataires réutilise `accessible_machine_ids()`
  (source de vérité `UserScope`) — aucune logique de périmètre dupliquée.

WebSocket : aucun serveur temps réel n'existe dans le projet. `dispatch()`
est le point d'accroche prévu pour y diffuser plus tard (voir §8 du cahier
des charges) sans rien changer au reste du module.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError

from .models import ORDRE_NIVEAUX, Alerte, Notification, PreferenceNotification

logger = logging.getLogger(__name__)


class NotificationService:
    """Point d'entrée unique de diffusion d'une alerte."""

    EVENEMENT_CREATION = 'CREATION'
    EVENEMENT_RETOUR_NORMALE = 'RETOUR_NORMALE'

    # ── Diffusion ──────────────────────────────────────────────────────────

    @classmethod
    def dispatch(cls, alerte, evenement=EVENEMENT_CREATION, destinataires=None) -> dict:
        """Notifie les utilisateurs ayant accès à la machine de l'alerte.

        Retourne un rapport par canal (utile pour les tests et la traçabilité).
        Ne lève jamais.
        """
        rapport = {
            'evenement': evenement,
            'in_app': 0,
            'email': 0,
            'email_ignores': 0,
            'sms': 0,
            'destinataires': 0,
        }

        try:
            if destinataires is None:
                destinataires = list(cls.destinataires_pour_machine(alerte.machine))
            rapport['destinataires'] = len(destinataires)

            if not destinataires:
                logger.info(
                    'Module 8 — aucun destinataire pour la machine %s : notification non diffusée.',
                    alerte.machine_id,
                )
                return rapport

            for utilisateur in destinataires:
                preference = cls.preference(utilisateur)
                if preference.in_app and settings.ALERTE_NOTIFICATIONS_IN_APP:
                    if cls.notify_in_app(utilisateur, alerte, evenement):
                        rapport['in_app'] += 1
                if evenement != cls.EVENEMENT_CREATION or not preference.email:
                    continue
                if not cls.niveau_concerne(preference, alerte.niveau):
                    rapport['email_ignores'] += 1
                    continue
                if cls.notify_email([preference.adresse_email], alerte):
                    rapport['email'] += 1
                else:
                    rapport['email_ignores'] += 1

            # Destinataires de repli définis par la configuration serveur.
            rapport['email'] += cls._notifier_destinataires_config(alerte, evenement)
            rapport['sms'] += cls.notify_sms(
                cls.telephones(destinataires), alerte,
            ) if (settings.ALERTE_NOTIFICATIONS_SMS and evenement == cls.EVENEMENT_CREATION) else 0

        except Exception:  # pragma: no cover - filet de sécurité
            logger.exception(
                'Module 8 — échec de la diffusion des notifications pour l\'alerte %s.',
                alerte.pk,
            )

        return rapport

    # ── Destinataires (périmètre = UserScope, source de vérité) ─────────────

    @staticmethod
    def destinataires_pour_machine(machine):
        """Utilisateurs actifs dont le périmètre `UserScope` ouvre `machine`.

        `ADMIN` est volontairement exclu : son accès est global, il voit
        toutes les alertes dans la liste et n'a pas besoin de notification.
        La vérification passe obligatoirement par
        `equipements.permissions.accessible_machine_ids()`.
        """
        from apps.accounts.models import Utilisateur

        accessibles = []
        for utilisateur in Utilisateur.objects.filter(
            actif=True, role__in=[Utilisateur.Role.TECHNICIEN, Utilisateur.Role.OPERATEUR]
        ):
            from apps.equipements.permissions import accessible_machine_ids

            if machine.pk in set(accessible_machine_ids(utilisateur)):
                accessibles.append(utilisateur)
        return accessibles

    @staticmethod
    def telephones(utilisateurs) -> list:
        return [u.telephone for u in utilisateurs if getattr(u, 'telephone', '')]

    @staticmethod
    def preference(utilisateur) -> PreferenceNotification:
        """Préférence de l'utilisateur, créée par défaut au premier envoi."""
        preference, _ = PreferenceNotification.objects.get_or_create(utilisateur=utilisateur)
        return preference

    @staticmethod
    def niveau_concerne(preference, niveau) -> bool:
        try:
            return ORDRE_NIVEAUX.index(niveau) >= ORDRE_NIVEAUX.index(preference.niveau_min_email)
        except ValueError:
            return True

    # ── Canal In-App ───────────────────────────────────────────────────────

    @staticmethod
    def notify_in_app(utilisateur, alerte, evenement=EVENEMENT_CREATION) -> bool:
        """Crée la notification In-App (idempotent grâce à la contrainte unique)."""
        if evenement == NotificationService.EVENEMENT_CREATION:
            type_notif = Notification.Type.ALERTE_CREEE
            titre = f'{alerte.get_niveau_display()} — {alerte.machine.nom}'
            message = alerte.message
        elif evenement == NotificationService.EVENEMENT_RETOUR_NORMALE:
            type_notif = Notification.Type.RETOUR_NORMALE
            titre = f'Retour à la normale — {alerte.machine.nom}'
            message = (
                f'{alerte.capteur.identifiant} : {alerte.derniere_valeur} '
                f'{alerte.unite} — plus de dépassement de seuil.'
            )
        else:
            type_notif = Notification.Type.INFO
            titre = 'Information'
            message = alerte.message

        try:
            Notification.objects.get_or_create(
                utilisateur=utilisateur,
                alerte=alerte,
                type=type_notif,
                defaults={
                    'titre': titre,
                    'message': message,
                    'niveau': alerte.niveau if type_notif != Notification.Type.RETOUR_NORMALE
                              else Alerte.Niveau.INFORMATION,
                },
            )
            return True
        except IntegrityError:
            return False

    # ── Canal Email ────────────────────────────────────────────────────────

    @staticmethod
    def smtp_configure() -> bool:
        """Le SMTP est-il réellement configuré dans l'environnement ?"""
        backend = getattr(settings, 'EMAIL_BACKEND', '') or ''
        if 'console' in backend or 'locmem' in backend:
            return False
        if not getattr(settings, 'EMAIL_HOST', ''):
            return False
        return bool(getattr(settings, 'EMAIL_HOST_USER', ''))

    @classmethod
    def notify_email(cls, destinataires, alerte) -> bool:
        """Envoie l'alerte par email. Ne lève jamais.

        Retourne ``True`` seulement si l'envoi a abouti.
        """
        destinataires = [d for d in (destinataires or []) if d]
        if not destinataires:
            return False

        if not settings.ALERTE_NOTIFICATIONS_EMAIL:
            logger.info(
                'Module 8 — canal email désactivé (ALERTE_NOTIFICATIONS_EMAIL=False) : '
                'alerte %s non envoyée.', alerte.pk,
            )
            return False

        if not cls.smtp_configure():
            logger.warning(
                "Module 8 — SMTP non configuré (EMAIL_HOST_USER / EMAIL_HOST absents) : "
                "l'alerte %s reste créée mais aucun email n'est envoyé.", alerte.pk,
            )
            return False

        from apps.accounts.email_utils import send_html_email

        sujet = f"[SmartFactory] {alerte.get_niveau_display()} — {alerte.machine.nom}"
        texte = (
            f"Alerte {alerte.reference}\n"
            f"Niveau     : {alerte.get_niveau_display()}\n"
            f"Machine    : {alerte.machine.nom} ({alerte.machine.identifiant_interne})\n"
            f"Capteur    : {alerte.capteur.identifiant}\n"
            f"Valeur     : {alerte.valeur} {alerte.unite}\n"
            f"Seuil      : {alerte.seuil} {alerte.unite}\n"
            f"Déclenchée : {alerte.date_declenchement:%d/%m/%Y %H:%M}\n"
            f"{alerte.message}\n"
        )
        html = (
            f'<p><strong>Alerte {alerte.reference}</strong> — '
            f'{alerte.get_niveau_display()}</p>'
            f'<ul>'
            f'<li><strong>Machine</strong> : {alerte.machine.nom} '
            f'({alerte.machine.identifiant_interne})</li>'
            f'<li><strong>Capteur</strong> : {alerte.capteur.identifiant}</li>'
            f'<li><strong>Valeur</strong> : {alerte.valeur} {alerte.unite}</li>'
            f'<li><strong>Seuil</strong> : {alerte.seuil} {alerte.unite}</li>'
            f'<li><strong>Déclenchée</strong> : {alerte.date_declenchement:%d/%m/%Y %H:%M}</li>'
            f'</ul><p>{alerte.message}</p>'
        )

        envoye = False
        for adresse in destinataires:
            try:
                send_html_email(sujet, texte, html, adresse, fail_silently=True)
                envoye = True
            except Exception as exc:  # pragma: no cover - dépend du SMTP
                logger.error(
                    "Module 8 — envoi email de l'alerte %s à %s impossible : %s",
                    alerte.pk, adresse, exc,
                )
        return envoye

    @classmethod
    def _notifier_destinataires_config(cls, alerte, evenement) -> int:
        """Destinataires de repli (configuration serveur), event CREATION seul."""
        if evenement != cls.EVENEMENT_CREATION or not settings.ALERTE_NOTIFICATIONS_EMAIL:
            return 0
        if ORDRE_NIVEAUX.index(alerte.niveau) < ORDRE_NIVEAUX.index(settings.ALERTE_EMAIL_NIVEAU_MIN):
            return 0
        adresses = [a.strip() for a in settings.ALERTE_NOTIFY_EMAILS if a.strip()]
        return 1 if adresses and cls.notify_email(adresses, alerte) else 0

    # ── Canal SMS (Twilio) — architecture uniquement ───────────────────────

    @staticmethod
    def notify_sms(numeros, alerte) -> int:
        """Canal SMS : PRÊT POUR UNE INTÉGRATION TWILIO FUTURE, NON ACTIVÉ.

        Twilio est optionnel : sans configuration, aucun SMS n'est envoyé et
        aucune erreur n'est levée. Le Module 8 ne dépend pas de ce canal.
        """
        numeros = [n for n in (numeros or []) if n]
        if not numeros or not settings.ALERTE_NOTIFICATIONS_SMS:
            return 0

        if not (getattr(settings, 'TWILIO_ACCOUNT_SID', '') and getattr(settings, 'TWILIO_AUTH_TOKEN', '')):
            logger.info(
                'Module 8 — canal SMS (Twilio) non configuré : aucun SMS envoyé pour l\'alerte %s.',
                alerte.pk,
            )
            return 0

        logger.warning(
            "Module 8 — l'envoi SMS via Twilio n'est pas implémenté dans ce sprint "
            "(Module 8 / §10) : %d destinataire(s) ignoré(s).", len(numeros),
        )
        return 0
