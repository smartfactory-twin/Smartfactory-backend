
import hashlib
import json
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import AuditLog
from apps.alertes.models import Alerte
from apps.equipements.models import Machine, OrdreTravail
from apps.equipements.serializers import OrdreTravailSerializer, RapportInterventionSerializer

from .models import VoiceActionProposal
from .tools import _call_api
from .speech import make_spoken_summary


WRITE_TOOLS = {
    'acknowledge_alert', 'create_work_order', 'update_work_order_status',
    'submit_work_order_report',
}


class ProposalError(Exception):
    pass


def _audit_proposal_event(proposal, action, status_code, details=None):
    user = proposal.utilisateur
    AuditLog.objects.create(
        acteur=user, acteur_email=user.email, acteur_role=user.role,
        action=f'VOICE {action} {proposal.outil}', methode='VOICE',
        chemin=f'/api/voice/proposals/{proposal.pk}/'[:512], code_http=status_code,
        details={
            'proposal_id': str(proposal.pk), 'outil': proposal.outil,
            'parametres': proposal.parametres,
            'status': proposal.statut, **(details or {}),
        },
    )


def _hash(parameters):
    serialized = json.dumps(parameters, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _api_get(request, path):
    payload, code = _call_api(request, 'GET', path)
    if code == 404:
        raise ProposalError('Objet introuvable ou hors de votre périmètre.')
    if code == 403:
        raise ProposalError('Votre rôle ne permet pas cette action.')
    if code >= 400:
        raise ProposalError('Impossible de vérifier l’objet auprès de l’API métier.')
    return payload


def validate_and_preview(request, tool, parameters):
    role = getattr(request.user, 'role', None)
    if tool == 'acknowledge_alert':
        comment = parameters.get('comment', '').strip()
        if not comment:
            raise ProposalError('Le commentaire d’acquittement est obligatoire.')
        alert = _api_get(request, f"/api/alertes/{parameters['alert_id']}/")
        if role not in {'ADMIN', 'TECHNICIEN', 'OPERATEUR'}:
            raise ProposalError('Votre rôle ne permet pas d’acquitter une alerte.')
        if alert.get('statut') != Alerte.Statut.ACTIVE:
            raise ProposalError('Cette alerte n’est plus active et ne peut pas être acquittée.')
        params = {'commentaire': comment}
        summary = f"Je vais acquitter l’alerte {alert.get('reference') or alert['id']} avec le commentaire {comment}."
        preview = {'alerte': alert.get('reference') or alert['id'], 'commentaire': comment}
        return params, summary[:250], make_spoken_summary(summary), preview, f"/api/alertes/{alert['id']}/acquitter/", 'POST'

    if tool == 'create_work_order':
        if role not in {'ADMIN', 'TECHNICIEN'}:
            raise ProposalError('Votre rôle ne permet pas de créer un ordre de travail.')
        machine_id = parameters['machine_id']
        machine_data = _api_get(request, f'/api/equipements/machines/{machine_id}/')
        machine = Machine.objects.filter(pk=machine_id).first()
        if not machine:
            raise ProposalError('Cette machine est introuvable.')
        title = parameters['title'].strip()
        assignee = parameters.get('assignee', '').strip()
        business_params = {
            'machine_id': machine_id, 'type': parameters['type'],
            'priorite': parameters['priority'], 'titre': title, 'assigne': assignee,
        }
        serializer = OrdreTravailSerializer(data=business_params, context={'request': request})
        serializer.is_valid(raise_exception=True)
        summary = f"Je vais créer un ordre de travail {parameters['type']} pour {machine.nom} : {title}."
        preview = {'machine': machine_data.get('nom'), **business_params}
        return business_params, summary[:250], make_spoken_summary(summary), preview, '/api/equipements/ordres-travail/', 'POST'

    if tool == 'update_work_order_status':
        if role not in {'ADMIN', 'TECHNICIEN'}:
            raise ProposalError('Votre rôle ne permet pas de modifier un ordre de travail.')
        order_id = parameters['work_order_id']
        order_data = _api_get(request, f'/api/equipements/ordres-travail/{order_id}/')
        order = OrdreTravail.objects.filter(pk=order_id).first()
        if not order:
            raise ProposalError('Ordre de travail introuvable.')
        next_status = parameters['status']
        serializer = OrdreTravailSerializer(
            order, data={'statut': next_status}, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        business_params = {'statut': next_status}
        summary = f"Je vais faire passer l’ordre de travail {order_id} de {order.statut} à {next_status}."
        preview = {'ordre': order_id, 'machine': order_data.get('machine_nom'),
                   'statut_actuel': order.statut, 'statut_proposé': next_status}
        return business_params, summary[:250], make_spoken_summary(summary), preview, f'/api/equipements/ordres-travail/{order_id}/', 'PATCH'

    if tool == 'submit_work_order_report':
        if role not in {'ADMIN', 'TECHNICIEN'}:
            raise ProposalError('Votre rôle ne permet pas de déposer un rapport.')
        order_id = parameters['work_order_id']
        order_data = _api_get(request, f'/api/equipements/ordres-travail/{order_id}/')
        if order_data.get('statut') not in (OrdreTravail.Statut.EN_COURS, OrdreTravail.Statut.ATTENTE_PIECES):
            raise ProposalError('Le rapport est autorisé uniquement pour un OT en cours ou en attente de pièces.')
        parts = parameters.get('parts', [])
        if not isinstance(parts, list) or len(parts) > 50:
            raise ProposalError('La liste des pièces est invalide.')
        business_params = {
            'travaux': parameters['work_done'].strip(), 'duree': parameters['duration'],
            'observations': parameters.get('observations', ''), 'pieces': parts,
            'signataire': parameters['signatory'].strip(),
        }
        serializer = RapportInterventionSerializer(data=business_params)
        serializer.is_valid(raise_exception=True)
        summary = f"Je vais déposer le rapport de l’ordre de travail {order_id}, signé par {business_params['signataire']}."
        preview = {'ordre': order_id, **business_params}
        return business_params, summary[:250], make_spoken_summary(summary), preview, f'/api/equipements/ordres-travail/{order_id}/rapport/', 'POST'
    raise ProposalError('Outil d’écriture inconnu.')


@transaction.atomic
def create_proposal(request, conversation, tool, parameters):
    from .models import VoiceConversation

    conversation = VoiceConversation.objects.select_for_update().get(pk=conversation.pk)
    params, summary, spoken, preview, path, method = validate_and_preview(request, tool, parameters)
    now = timezone.now()
    hourly_limit = max(1, int(settings.VOICE_PROPOSAL_HOURLY_LIMIT))
    if VoiceActionProposal.objects.filter(utilisateur=request.user, created_at__gte=now - timedelta(hours=1)).count() >= hourly_limit:
        raise ProposalError('Limite horaire de propositions atteinte.')
    replaced = list(VoiceActionProposal.objects.filter(
        utilisateur=request.user, conversation=conversation,
        statut=VoiceActionProposal.Status.PENDING,
    ))
    for old in replaced:
        old.statut = VoiceActionProposal.Status.CANCELLED
        old.erreur = 'Remplacée par une nouvelle proposition.'
        old.save(update_fields=['statut', 'erreur'])
        _audit_proposal_event(old, 'cancelled_replaced', 200)
    ttl = max(1, int(settings.VOICE_PROPOSAL_TTL_SECONDS))
    proposal = VoiceActionProposal.objects.create(
        utilisateur=request.user, conversation=conversation, outil=tool,
        parametres=params, parametres_hash=_hash(params), resume=summary,
        apercu=preview, spoken_summary=spoken,
        expires_at=now + timedelta(seconds=ttl),
    )
    _audit_proposal_event(proposal, 'created', 201, {'spoken_summary': spoken})
    return proposal, path, method


@transaction.atomic
def expire_if_needed(proposal):
    proposal = VoiceActionProposal.objects.select_for_update().get(pk=proposal.pk)
    if proposal.statut == VoiceActionProposal.Status.PENDING and proposal.expires_at <= timezone.now():
        proposal.statut = VoiceActionProposal.Status.EXPIRED
        proposal.erreur = 'La proposition a expiré.'
        proposal.save(update_fields=['statut', 'erreur'])
        _audit_proposal_event(proposal, 'expired', 410)
    return proposal


def execute_proposal(request, proposal):
    if _hash(proposal.parametres) != proposal.parametres_hash:
        raise ProposalError('Les paramètres de la proposition ont été altérés.')
    # Revalidate current role, scope, object state, and serializer rules at commit time.
    _, _, _, _, path, method = validate_and_preview(request, proposal.outil, _tool_arguments(proposal))
    result, code = _call_api(request, method, path, payload=proposal.parametres)
    if code >= 400:
        raise ProposalError(f"L’API métier a refusé l’action ({code}).")
    return result, path, method


def _tool_arguments(proposal):
    params = proposal.parametres
    if proposal.outil == 'acknowledge_alert':
        return {'alert_id': int(proposal.apercu['alerte'].split('-')[-1]) if isinstance(proposal.apercu['alerte'], str) and proposal.apercu['alerte'].split('-')[-1].isdigit() else proposal.apercu['alerte'], 'comment': params['commentaire']}
    if proposal.outil == 'create_work_order':
        return {'machine_id': params['machine_id'], 'type': params['type'], 'priority': params['priorite'], 'title': params['titre'], 'assignee': params['assigne']}
    if proposal.outil == 'update_work_order_status':
        return {'work_order_id': int(proposal.apercu['ordre']), 'status': params['statut']}
    return {'work_order_id': int(proposal.apercu['ordre']), 'work_done': params['travaux'], 'duration': params['duree'], 'observations': params['observations'], 'parts': params['pieces'], 'signatory': params['signataire']}


def write_audit_event(request, proposal, method, path, status_code, result=None, duration_ms=0, error=''):
    user = request.user
    AuditLog.objects.create(
        acteur=user, acteur_email=user.email, acteur_role=user.role,
        action=f'{method} voice.proposal.{proposal.statut}', methode=method,
        chemin=path[:512], code_http=status_code,
        adresse_ip=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
        details={
            'outil': proposal.outil, 'parametres': proposal.parametres,
            'resultat': result if isinstance(result, dict) else {},
            'duree_ms': duration_ms, 'erreur': error[:500],
            'proposal_id': str(proposal.pk),
        },
    )
