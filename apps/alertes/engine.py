"""Module 8 — Moteur de déclenchement des alertes (UC-26 / UC-27).

Point d'entrée unique : `evaluer_lecture(reading)`. Il est appelé par le
signal `post_save` sur `Reading` (voir `signals.py`), donc **par tous** les
chemins d'ingestion existants : `POST /api/readings/`, `import_csv`,
`import_json`, action `preprocess`. Aucune logique parallèle.

── Logique de déclenchement ────────────────────────────────────────────────────

1. La mesure est ignorée si la mesure est *interpolée* (`Reading.interpolation`)
   : on n'alerte pas sur une valeur inventée par le Module 3.
2. La surveillance est ignorée si `Sensor.actif` est `False` : c'est
   l'activation/désactivation de la surveillance demandée par l'UC-26.
3. Si `valeur < Sensor.seuil_min` → type `SEUIL_MIN` ; si
   `valeur > Sensor.seuil_max` → type `SEUIL_MAX`. Sinon, retour à la
   normale : les alertes ouvertes du capteur sont résolues.

Le **statut de la machine n'est jamais modifié** ici : la machine garde sa
propre logique de statut.

── Niveau (UC-27) — règle explicite, sans IA, configurable ─────────────────────

Deux métriques sont calculées à partir des seuils *existants* du capteur :

* `depassement      = |valeur − seuil franchi|`
* `ratio_plage_pct  = depassement / (seuil_max − seuil_min) × 100`
  (toujours défini : `Sensor.clean()` garantit `seuil_min < seuil_max`)

Puis, dans cet ordre :

* `CRITIQUE` si `ratio_plage_pct >= ALERTE_CRITIQUE_RATIO_PCT`
              **ou** `depassement   >= ALERTE_CRITIQUE_DEPASSEMENT`
* `MAJEURE`   si `ratio_plage_pct >= ALERTE_MAJEURE_RATIO_PCT`
              **ou** `depassement   >= ALERTE_MAJEURE_DEPASSEMENT`
* `MINEURE`   sinon.

Les quatre seuils viennent de `core/settings.py` (donc de l'environnement) :
modifier la logique de gravité ne demande **aucun changement de code**.

`INFORMATION` existe dans le modèle pour un usage futur ; aucune règle de
seuil ne le produit dans ce sprint.

── Anti-duplication ───────────────────────────────────────────────────────────

Une seule alerte **ouverte** (ACTIVE ou ACKNOWLEDGED) par capteur et par
direction. Conséquences :

* 10:00 → 105 °C → *alerte créée* ;
* 10:01 → 106 °C → *aucune nouvelle alerte*, `nb_occurrences` incrémenté,
  `derniere_valeur` / `derniere_occurrence` mises à jour ;
* 10:02 → 107 °C → idem.

L'alerte reste ouverte jusqu'au traitement. Si la situation s'aggrave
(ex. la valeur monte et change de niveau), le **niveau est escaladé sur
l'alerte existante** — on ne crée pas de doublon, et on ne renvoie pas de
notification (anti-spam).

Retour à la normale : toutes les alertes ouvertes du capteur passent en
`RESOLVED` avec `date_resolution` + motif, **et** une unique notification
« Retour à la normale » est envoyée. Le cycle suivant repart d'une alerte
neuve, sans spam.

La garantie est aussi posée en base : contrainte unique partielle
`alerte_unique_ouverte_par_capteur` sur `(capteur, type_alerte)` filtrée
sur `statut IN (ACTIVE, ACKNOWLEDGED)`.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import ORDRE_NIVEAUX, Alerte

logger = logging.getLogger(__name__)

STATUTS_OUVERTS = (Alerte.Statut.ACTIVE, Alerte.Statut.ACKNOWLEDGED)


# ── UC-26 — Règles d'alerte (seuils existants du capteur) ───────────────────

def evaluer_seuil(valeur, seuil_min, seuil_max) -> dict | None:
    """Retourne le dépassement constaté, ou ``None`` si la valeur est normale.

    Le retour contient ``type_alerte``, ``seuil``, ``depassement`` et
    ``ratio_plange_pct`` — tout ce dont le niveau a besoin.
    """
    if valeur < seuil_min:
        seuil = seuil_min
        type_alerte = Alerte.TypeAlerte.SEUIL_MIN
    elif valeur > seuil_max:
        seuil = seuil_max
        type_alerte = Alerte.TypeAlerte.SEUIL_MAX
    else:
        return None

    depassement = abs(valeur - seuil)
    plage = (seuil_max - seuil_min) or 1.0
    return {
        'type_alerte': type_alerte,
        'seuil': float(seuil),
        'depassement': float(depassement),
        'ratio_plage_pct': round(float(depassement) / float(plage) * 100.0, 2),
    }


# ── UC-27 — Niveaux (règle explicite, sans IA) ───────────────────────────────

def determiner_niveau(depassement, ratio_plage_pct) -> str:
    """Applique la règle de gravité décrite dans la docstring du module."""
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
    """Compare deux niveaux via l'ordre de gravité croissant."""
    return niveau_a if ORDRE_NIVEAUX.index(niveau_a) >= ORDRE_NIVEAUX.index(niveau_b) else niveau_b


def construire_message(capteur, type_alerte, valeur, seuil, unite) -> str:
    unite_txt = f' {unite}' if unite else ''
    return (
        f'{capteur.identifiant} — {dict(Alerte.TypeAlerte.choices)[type_alerte]} : '
        f'{valeur}{unite_txt} (seuil {seuil}{unite_txt}).'
    )


# ── Génération automatique ──────────────────────────────────────────────────

@transaction.atomic
def evaluer_lecture(reading) -> dict:
    """Évalue une mesure et met à jour les alertes du capteur.

    Ne lève jamais d'exception métier : renvoie un rapport exploitable.
    """
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
    """Une alerte ouverte par (capteur, direction) : on incrémente, sinon on crée."""
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
    """Retour à la normale : clôt les alertes ouvertes, sans spam."""
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
            f'({capteur.seuil_min} – {capteur.seuil_max} {capteur.unite}).'
        ).strip()
        if alerte.resoudre(motif):
            resolues.append(alerte)

    for alerte in resolues:
        NotificationService.dispatch(
            alerte, evenement=NotificationService.EVENEMENT_RETOUR_NORMALE,
        )

    return {'action': 'resolues', 'alertes': resolues, 'nb': len(resolues)}
