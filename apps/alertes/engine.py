from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import ORDRE_NIVEAUX, Alerte

logger = logging.getLogger(__name__)

STATUTS_OUVERTS = (Alerte.Statut.ACTIVE, Alerte.Statut.ACKNOWLEDGED)


# Règles d'alerte (seuils existants du capteur)

def evaluer_seuil(valeur, seuil_min, seuil_max) -> dict | None:

    if seuil_min is not None and valeur < seuil_min:
        seuil = seuil_min
        type_alerte = Alerte.TypeAlerte.SEUIL_MIN
    elif seuil_max is not None and valeur > seuil_max:
        seuil = seuil_max
        type_alerte = Alerte.TypeAlerte.SEUIL_MAX
    else:
        return None

    depassement = abs(valeur - seuil)
    plage = (seuil_max - seuil_min) if seuil_min is not None and seuil_max is not None else None
    ratio_plage_pct = round(float(depassement) / float(plage) * 100.0, 2) if plage else 0.0
    return {
        'type_alerte': type_alerte,
        'seuil': float(seuil),
        'depassement': float(depassement),
        'ratio_plage_pct': ratio_plage_pct,
    }


#  Niveaux (règle explicite, sans IA)

def determiner_niveau(depassement, ratio_plage_pct) -> str:
   
    if (
        ratio_plage_pct >= settings.ALERTE_CRITIQUE_RATIO_PCT
        or depassement >= settings.ALERTE_CRITIQUE_DEPASSEMENT
    ):
        return Alerte.Niveau.CRITIQUE
    if (
        ratio_plage_pct >= settings.ALERTE_MAJEURE_RATIO_PCT
        or depassement >= settings.ALERTE_MAJEURE_DEPASSEMENT
    ):
        return Alerte.Niveau.MAJEURE
    return Alerte.Niveau.MINEURE


def niveau_plus_grave(niveau_a, niveau_b) -> str:
    
    return niveau_a if ORDRE_NIVEAUX.index(niveau_a) >= ORDRE_NIVEAUX.index(niveau_b) else niveau_b


def construire_message(capteur, type_alerte, valeur, seuil, unite) -> str:
    unite_txt = f' {unite}' if unite else ''
    return (
        f'{capteur.identifiant} — {dict(Alerte.TypeAlerte.choices)[type_alerte]} : '
        f'{valeur}{unite_txt} (seuil {seuil}{unite_txt}).'
    )


#  Génération automatique 
@transaction.atomic
def evaluer_lecture(reading) -> dict:
  
    capteur = reading.sensor

    if reading.interpolation:
        return {'action': 'ignoree', 'raison': 'mesure interpolée'}

    if not capteur.actif:
        return {'action': 'ignoree', 'raison': 'surveillance désactivée sur le capteur'}

    depassement = evaluer_seuil(
        reading.valeur, capteur.seuil_min, capteur.seuil_max,
    )

    if depassement is None:
        return _resoudre_si_normal(capteur, reading)

    return _ouvrir_ou_incrementer(capteur, reading, depassement)


def _ouvrir_ou_incrementer(capteur, reading, depassement) -> dict:
    
    niveau = determiner_niveau(depassement['depassement'], depassement['ratio_plage_pct'])

    # `select_for_update` sérialise les ingérations concurrentes sur un même
    # capteur (sans effet sur SQLite, actif sur PostgreSQL).
    ouverte = (
        Alerte.objects.select_for_update()
        .filter(capteur=capteur, type_alerte=depassement['type_alerte'], statut__in=STATUTS_OUVERTS)
        .order_by('-date_declenchement')
        .first()
    )

    if ouverte is not None:
        niveau_precedent = ouverte.niveau
        ouverte.nb_occurrences = (ouverte.nb_occurrences or 0) + 1
        ouverte.derniere_valeur = reading.valeur
        ouverte.derniere_occurrence = reading.timestamp
        escalate = ORDRE_NIVEAUX.index(niveau) > ORDRE_NIVEAUX.index(ouverte.niveau)
        if escalate:
            # Escalade sur l'alerte existante : pas de doublon, pas de
            # nouvelle notification (anti-spam).
            ouverte.niveau = niveau
        if ouverte.statut == Alerte.Statut.ACTIVE:
            # Le message reflète la dernière valeur tant que l'alerte n'a pas
            # été acquittée : après acquittement, il fige l'état traité.
            ouverte.message = construire_message(
                capteur, ouverte.type_alerte, reading.valeur, ouverte.seuil, capteur.unite,
            )
        ouverte.save(update_fields=[
            'nb_occurrences', 'derniere_valeur', 'derniere_occurrence',
            'niveau', 'message', 'updated_at',
        ])
        return {
            'action': 'incrementee',
            'alerte': ouverte,
            'niveau_precedent': niveau_precedent,
            'escalade': escalate,
        }

    try:
        with transaction.atomic():
            alerte = Alerte.objects.create(
                machine=capteur.machine,
                capteur=capteur,
                lecture=reading,
                type_alerte=depassement['type_alerte'],
                niveau=niveau,
                valeur=reading.valeur,
                seuil=depassement['seuil'],
                unite=capteur.unite,
                depassement=depassement['depassement'],
                ratio_plage_pct=depassement['ratio_plage_pct'],
                message=construire_message(
                    capteur, depassement['type_alerte'],
                    reading.valeur, depassement['seuil'], capteur.unite,
                ),
                nb_occurrences=1,
                derniere_valeur=reading.valeur,
                derniere_occurrence=reading.timestamp,
                date_declenchement=reading.timestamp,
            )
    except IntegrityError:
        # Course perdue : une alerte ouverte a été créée entre-temps.
        logger.info(
            'Module 8 — alerte déjà ouverte pour le capteur %s (%s), création ignorée.',
            capteur.identifiant, depassement['type_alerte'],
        )
        return {'action': 'doublon_evite'}

    from .notifications import NotificationService
    NotificationService.dispatch(alerte, evenement=NotificationService.EVENEMENT_CREATION)

    return {'action': 'creee', 'alerte': alerte}


def _resoudre_si_normal(capteur, reading) -> dict:
   
    if not getattr(settings, 'ALERTE_RESOLUTION_AUTO', True):
        return {'action': 'aucune'}

    ouvertes = list(
        Alerte.objects.select_for_update()
        .filter(capteur=capteur, statut__in=STATUTS_OUVERTS)
        .order_by('date_declenchement')
    )
    if not ouvertes:
        return {'action': 'aucune'}

    from .notifications import NotificationService

    resolues = []
    for alerte in ouvertes:
        motif = (
            f'Reprise dans la plage autorisée du capteur '
            f'({capteur.seuil_min if capteur.seuil_min is not None else "−∞"} – '
            f'{capteur.seuil_max if capteur.seuil_max is not None else "+∞"} {capteur.unite}).'
        ).strip()
        if alerte.resoudre(motif):
            resolues.append(alerte)

    for alerte in resolues:
        NotificationService.dispatch(
            alerte, evenement=NotificationService.EVENEMENT_RETOUR_NORMALE,
        )

    return {'action': 'resolues', 'alertes': resolues, 'nb': len(resolues)}
