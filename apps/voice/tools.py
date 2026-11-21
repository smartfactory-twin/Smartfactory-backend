"""Allowlisted, read-only tools implemented by dispatching existing DRF routes."""
import json
from datetime import datetime, timezone as dt_timezone
from io import BytesIO
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from django.core.handlers.wsgi import WSGIRequest
from django.urls import resolve


MAX_TOOL_RESPONSE_BYTES = 12_000
MAX_FREE_TEXT = 240
MAX_PERIOD_DAYS = 366


def data_text(value):
    """Mark all database/user-supplied strings as data and bound their size."""
    return {'kind': 'untrusted_data', 'value': str(value or '')[:MAX_FREE_TEXT]}


TOOL_SCHEMAS = [
    ('search_machines', 'Rechercher des machines visibles dans le périmètre utilisateur.', {
        'query': {'type': 'string', 'minLength': 1, 'maxLength': 100},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 10},
    }, ['query']),
    ('get_machine', 'Obtenir une machine par identifiant interne exact ou nom exact.', {
        'machine_ref': {'type': 'string', 'minLength': 1, 'maxLength': 100},
    }, ['machine_ref']),
    ('list_sensors', 'Lister les capteurs d’une machine visible.', {
        'machine_id': {'type': 'integer', 'minimum': 1},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
    }, ['machine_id']),
    ('get_sensor_readings', 'Lire des mesures récentes d’un capteur visible.', {
        'sensor_id': {'type': 'integer', 'minimum': 1},
        'date_debut': {'type': 'string', 'maxLength': 40},
        'date_fin': {'type': 'string', 'maxLength': 40},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
    }, ['sensor_id']),
    ('list_alerts', 'Lister les alertes visibles avec filtres bornés.', {
        'machine_id': {'type': 'integer', 'minimum': 1},
        'niveau': {'type': 'string', 'enum': ['INFORMATION', 'MINEURE', 'MAJEURE', 'CRITIQUE']},
        'statut': {'type': 'string', 'enum': ['ACTIVE', 'ACKNOWLEDGED', 'RESOLVED']},
        'date_debut': {'type': 'string', 'maxLength': 40},
        'date_fin': {'type': 'string', 'maxLength': 40},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
    }, []),
    ('get_alerts_by_machine', 'Compter les alertes visibles par machine sur une période.', {
        'date_debut': {'type': 'string', 'maxLength': 40},
        'date_fin': {'type': 'string', 'maxLength': 40},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50},
    }, ['date_debut', 'date_fin']),
    ('get_alert', 'Obtenir une alerte visible par identifiant numérique ou référence exacte.', {
        'alert_ref': {'type': 'string', 'minLength': 1, 'maxLength': 40},
    }, ['alert_ref']),
    ('list_work_orders', 'Lister les ordres de travail visibles.', {
        'machine_id': {'type': 'integer', 'minimum': 1},
        'statut': {'type': 'string', 'enum': ['Créé', 'Assigné', 'En cours', 'En attente pièces', 'Rapport déposé', 'Validé', 'Clôturé']},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
    }, []),
    ('get_work_order', 'Obtenir un ordre de travail visible par ID.', {
        'work_order_id': {'type': 'integer', 'minimum': 1},
    }, ['work_order_id']),
    ('get_anomaly_summary', 'Lire le résumé statistique d’anomalies d’une machine visible.', {
        'machine_id': {'type': 'integer', 'minimum': 1},
    }, ['machine_id']),
    ('simulate_what_if', 'Calculer un scénario statistique sans persister de mesure.', {
        'sensor_id': {'type': 'integer', 'minimum': 1},
        'variation_percent': {'type': 'number', 'minimum': -100, 'maximum': 300},
    }, ['sensor_id', 'variation_percent']),
    ('get_model_availability', 'Lire la disponibilité IA des machines du périmètre.', {
        'machine_id': {'type': 'integer', 'minimum': 1},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
    }, []),
    ('get_rul_status', 'Indiquer si une RUL fiable est disponible pour une machine.', {
        'machine_ref': {'type': 'string', 'maxLength': 100},
    }, []),
]


LLM_TOOLS = [{
    'type': 'function',
    'function': {
        'name': name,
        'description': description,
        'parameters': {
            'type': 'object', 'properties': properties,
            'required': required, 'additionalProperties': False,
        },
    },
} for name, description, properties, required in TOOL_SCHEMAS]

TOOL_PROPERTIES = {name: properties for name, _, properties, _ in TOOL_SCHEMAS}
TOOL_REQUIRED = {name: set(required) for name, _, _, required in TOOL_SCHEMAS}


class ToolCallError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _validate_arguments(name, arguments):
    if name not in TOOL_PROPERTIES:
        raise ToolCallError('unknown_tool', 'Le modèle a demandé un outil non autorisé.')
    if not isinstance(arguments, dict):
        raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
    schema = TOOL_PROPERTIES[name]
    if set(arguments) - set(schema) or TOOL_REQUIRED[name] - set(arguments):
        raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
    for key, value in arguments.items():
        rule = schema[key]
        kind = rule['type']
        valid_type = (isinstance(value, str) if kind == 'string' else
                      isinstance(value, (int, float)) and not isinstance(value, bool) if kind == 'number' else
                      isinstance(value, int) and not isinstance(value, bool))
        if not valid_type:
            raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
        if kind == 'string' and (len(value) > rule.get('maxLength', 1000) or len(value) < rule.get('minLength', 0)):
            raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
        if kind in ('number', 'integer') and not rule.get('minimum', float('-inf')) <= value <= rule.get('maximum', float('inf')):
            raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
        if 'enum' in rule and value not in rule['enum']:
            raise ToolCallError('invalid_tool_arguments', 'Les paramètres de l’outil sont invalides.')
    if 'date_debut' in arguments or 'date_fin' in arguments:
        if not arguments.get('date_debut') or not arguments.get('date_fin'):
            raise ToolCallError('invalid_tool_arguments', 'Les deux bornes de période sont requises ensemble.')
        start = _parse_date(arguments['date_debut'])
        end = _parse_date(arguments['date_fin'])
        if start >= end or (end - start).total_seconds() > MAX_PERIOD_DAYS * 86400:
            raise ToolCallError('invalid_tool_arguments', 'La période est invalide ou dépasse 366 jours.')
    return dict(arguments)


def _parse_date(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        raise ToolCallError('invalid_tool_arguments', 'Les dates doivent être au format ISO-8601.') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ToolCallError('invalid_tool_arguments', 'Les dates doivent inclure un fuseau horaire.')
    return parsed.astimezone(dt_timezone.utc)


def _call_api(request, method, path, query=None, payload=None):
    """Dispatch the existing URL callback in-process with the caller JWT.

    The route's own authentication, permission, queryset, scope, serializer,
    and throttling code remains authoritative. The token is not put in model
    messages or persisted in the voice audit table.
    """
    query_string = urlencode(query or {})
    if query_string:
        path = f'{path}?{query_string}'
    route_path = path.split('?', 1)[0]
    body = json.dumps(payload).encode('utf-8') if payload is not None else b''
    environ = {}
    setup_testing_defaults(environ)
    environ.update({
        'REQUEST_METHOD': method,
        'PATH_INFO': route_path,
        'QUERY_STRING': query_string,
        'CONTENT_TYPE': 'application/json',
        'CONTENT_LENGTH': str(len(body)),
        'wsgi.input': BytesIO(body),
    })
    authorization = request.headers.get('Authorization', '')
    if authorization:
        environ['HTTP_AUTHORIZATION'] = authorization
    try:
        inner_request = WSGIRequest(environ)
        match = resolve(route_path)
        response = match.func(inner_request, *match.args, **match.kwargs)
        if hasattr(response, 'render'):
            response.render()
        status_code = response.status_code
        if not 200 <= status_code < 300:
            code = 'not_found' if status_code == 404 else 'forbidden' if status_code == 403 else 'api_error'
            return {'error': code, 'http_status': status_code}, status_code
        return json.loads(response.content.decode('utf-8')), status_code
    except Exception:
        return {'error': 'api_unavailable'}, 503


def _bounded(payload):
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) <= MAX_TOOL_RESPONSE_BYTES:
        return payload
    return {
        'truncated': True,
        'incomplete': True,
        'detail': 'Le résultat dépasse la limite de taille ; contenu omis.',
    }


def _paged_rows(request, path, params, limit, mapper):
    page, status_code = _call_api(request, 'GET', path, params)
    if status_code >= 400:
        return {'error': page['error'], 'truncated': False, 'incomplete': False}
    rows = page.get('results', page if isinstance(page, list) else [])
    rows = rows if isinstance(rows, list) else []
    result = [mapper(row) for row in rows[:limit]]
    truncated = bool(page.get('next')) if isinstance(page, dict) else False
    truncated = truncated or len(rows) > limit
    return {'results': result, 'count_returned': len(result), 'truncated': truncated, 'incomplete': truncated}


def _machine(row):
    return {
        'id': row.get('id'), 'nom': data_text(row.get('nom')),
        'identifiant': data_text(row.get('identifiant_interne')),
        'statut': data_text(row.get('statut_label') or row.get('statut')),
    }


def _sensor(row):
    return {
        'id': row.get('id'), 'nom': data_text(row.get('nom')),
        'identifiant': data_text(row.get('identifiant')),
        'machine_id': row.get('machine'), 'type': data_text(row.get('type_capteur')),
        'role': data_text(row.get('sensor_role')), 'unit': data_text(row.get('unit') or row.get('unite')),
        'threshold_min': row.get('seuil_min'), 'threshold_max': row.get('seuil_max'),
    }


def _alert(row):
    return {
        'id': row.get('id'), 'reference': data_text(row.get('reference')),
        'machine_id': row.get('machine'), 'machine': data_text(row.get('machine_nom')),
        'sensor_id': row.get('capteur'), 'sensor': data_text(row.get('capteur_nom')),
        'level': data_text(row.get('niveau_label') or row.get('niveau')),
        'status': data_text(row.get('statut_label') or row.get('statut')),
        'value': row.get('valeur'), 'unit': data_text(row.get('unite')),
        'message': data_text(row.get('message')),
        'created_at': row.get('date_declenchement'),
    }


def _work_order(row):
    return {
        'id': row.get('id'), 'machine_id': row.get('machine_id'),
        'machine': data_text(row.get('machine_nom')), 'type': data_text(row.get('type')),
        'priority': data_text(row.get('priorite')), 'status': data_text(row.get('statut')),
        'title': data_text(row.get('titre')), 'assignee': data_text(row.get('assigne')),
        'due_at': row.get('echeance'),
    }


def _machine_match(request, reference):
    response, code = _call_api(request, 'GET', '/api/equipements/machines/', {'search': reference, 'page_size': 100})
    if code >= 400:
        return None, {'error': response['error']}
    matches = [row for row in response.get('results', []) if
               str(row.get('identifiant_interne', '')).casefold() == reference.casefold() or
               str(row.get('nom', '')).casefold() == reference.casefold()]
    if response.get('next'):
        return None, {'error': 'incomplete_search', 'truncated': True, 'incomplete': True}
    if len(matches) != 1:
        return None, {'error': 'not_found' if not matches else 'ambiguous', 'truncated': False, 'incomplete': False}
    return matches[0], None


def execute_tool(request, name, raw_arguments):
    args = _validate_arguments(name, raw_arguments)
    limit = args.get('limit', 10)

    if name == 'search_machines':
        return _bounded(_paged_rows(request, '/api/equipements/machines/', {'search': args['query']}, limit, _machine))
    if name == 'get_machine':
        row, error = _machine_match(request, args['machine_ref'])
        if error:
            return _bounded(error)
        result, code = _call_api(request, 'GET', f"/api/equipements/machines/{row['id']}/")
        return _bounded({'machine': _machine(result), 'truncated': False, 'incomplete': False}
                        if code < 400 else {'error': result['error'], 'truncated': False, 'incomplete': False})
    if name == 'list_sensors':
        return _bounded(_paged_rows(request, '/api/equipements/capteurs/',
                                    {'machine': args['machine_id']}, limit, _sensor))
    if name == 'get_sensor_readings':
        params = {'sensor': args['sensor_id'], 'page_size': limit, 'ordering': '-timestamp'}
        if args.get('date_debut'):
            params['timestamp__gte'] = args['date_debut']
            params['timestamp__lte'] = args['date_fin']
        response, code = _call_api(request, 'GET', '/api/equipements/readings/', params)
        if code >= 400:
            return _bounded({'error': response['error'], 'truncated': False, 'incomplete': False})
        rows = response.get('results', [])
        return _bounded({
            'results': [{
                'id': row.get('id'), 'sensor_id': row.get('sensor'),
                'value': row.get('valeur', row.get('value')), 'timestamp': row.get('timestamp'),
                'valid': row.get('est_valide'),
            } for row in rows[:limit]],
            'count_returned': min(len(rows), limit),
            'truncated': bool(response.get('next')) or len(rows) > limit,
            'incomplete': bool(response.get('next')) or len(rows) > limit,
        })
    if name == 'list_alerts':
        params = {'page_size': limit, 'ordering': '-date_declenchement'}
        for source, dest in [('machine_id', 'machine'), ('niveau', 'niveau'), ('statut', 'statut')]:
            if source in args:
                params[dest] = args[source]
        if args.get('date_debut'):
            params['date_declenchement__gte'] = args['date_debut']
            params['date_declenchement__lte'] = args['date_fin']
        return _bounded(_paged_rows(request, '/api/alertes/', params, limit, _alert))
    if name == 'get_alerts_by_machine':
        response, code = _call_api(request, 'GET', '/api/alertes/aggregation/par-machine/', {
            'date_debut': args['date_debut'], 'date_fin': args['date_fin'],
            'limit': args.get('limit', 20),
        })
        if code >= 400:
            return _bounded({'error': response['error'], 'truncated': False, 'incomplete': False})
        rows = response.get('results', [])
        truncated = bool(response.get('truncated'))
        return _bounded({
            'results': [{
                'machine_id': row.get('machine_id'),
                'machine': data_text(row.get('machine')),
                'machine_identifiant': data_text(row.get('identifiant_interne')),
                'alert_count': row.get('alert_count'),
            } for row in rows],
            'count': response.get('count'), 'period': response.get('period'),
            'truncated': truncated, 'incomplete': truncated,
        })
    if name == 'get_alert':
        reference = args['alert_ref']
        if reference.isdigit():
            path = f'/api/alertes/{int(reference)}/'
        else:
            candidates, code = _call_api(request, 'GET', '/api/alertes/', {'search': reference, 'page_size': 100})
            if code >= 400:
                return _bounded({'error': candidates['error']})
            if candidates.get('next'):
                return _bounded({'error': 'incomplete_search', 'truncated': True, 'incomplete': True})
            exact = [r for r in candidates.get('results', []) if r.get('reference') == reference]
            if len(exact) != 1:
                return _bounded({'error': 'not_found' if not exact else 'ambiguous'})
            path = f"/api/alertes/{exact[0]['id']}/"
        row, code = _call_api(request, 'GET', path)
        return _bounded({'alert': _alert(row), 'truncated': False, 'incomplete': False}
                        if code < 400 else {'error': row['error'], 'truncated': False, 'incomplete': False})
    if name == 'list_work_orders':
        params = {}
        if 'machine_id' in args:
            params['machine'] = args['machine_id']
        if 'statut' in args:
            params['statut'] = args['statut']
        return _bounded(_paged_rows(request, '/api/equipements/ordres-travail/', params, limit, _work_order))
    if name == 'get_work_order':
        row, code = _call_api(request, 'GET', f"/api/equipements/ordres-travail/{args['work_order_id']}/")
        if code >= 400:
            return _bounded({'error': row['error'], 'truncated': False, 'incomplete': False})
        item = _work_order(row)
        item['history_count'] = len(row.get('historique') or [])
        report = row.get('rapport') or {}
        item['report'] = {
            'work': data_text(report.get('travaux')),
            'observations': data_text(report.get('observations')),
        } if report else None
        return _bounded({'work_order': item, 'truncated': False, 'incomplete': False})
    if name == 'get_anomaly_summary':
        row, code = _call_api(request, 'GET', '/api/ai-predictions/anomalies/', {'machine_id': args['machine_id']})
        if code >= 400:
            return _bounded({'error': row['error'], 'truncated': False, 'incomplete': False})
        history = row.get('history', [])
        alerts = row.get('alerts', [])
        return _bounded({
            'machine': {'id': (row.get('machine') or {}).get('id'),
                        'name': data_text((row.get('machine') or {}).get('nom'))},
            'score': row.get('score'), 'threshold': row.get('threshold'),
            'detected': row.get('detected'),
            'method': data_text(row.get('method')),
            'history': [{
                'timestamp': point.get('timestamp'), 'score': point.get('score'),
            } for point in history[-10:]], 'history_truncated': len(history) > 10,
            'alerts': [{
                'id': a.get('id'), 'sensor': data_text(a.get('sensor')),
                'message': data_text(a.get('message')), 'status': data_text(a.get('status')),
                'score': a.get('score'), 'timestamp': a.get('timestamp'),
            } for a in alerts[:10]],
            'alerts_truncated': len(alerts) > 10,
            'truncated': len(history) > 10 or len(alerts) > 10,
            'incomplete': len(history) > 10 or len(alerts) > 10,
        })
    if name == 'simulate_what_if':
        row, code = _call_api(request, 'POST', '/api/ai-predictions/what-if/', payload={
            'sensor_id': args['sensor_id'], 'variation_percent': args['variation_percent'],
        })
        if code >= 400:
            return _bounded({'error': row['error'], 'truncated': False, 'incomplete': False})
        result = {key: (data_text(value) if key in ('machine', 'sensor', 'unit', 'method') else value)
                  for key, value in row.items()}
        result.update({'truncated': False, 'incomplete': False})
        return _bounded(result)
    if name == 'get_model_availability':
        row, code = _call_api(request, 'GET', '/api/ai/readiness/')
        if code >= 400:
            return _bounded({'error': row['error'], 'reason': 'role_or_scope_denied',
                             'truncated': False, 'incomplete': False})
        machines = row.get('machines', [])
        if 'machine_id' in args:
            machines = [m for m in machines if m.get('machine_id') == args['machine_id']]
        result = machines[:limit]
        return _bounded({
            'criteria': row.get('criteria'),
            'machines': [{
                'machine_id': m.get('machine_id'), 'machine': data_text(m.get('machine')),
                'machine_identifiant': data_text(m.get('machine_identifiant')),
                'eligible_sensor_count': m.get('eligible_sensor_count'),
                'valid_measure_count': m.get('valid_measure_count'),
                'history_days': m.get('history_days'), 'missing_rate_percent': m.get('missing_rate_percent'),
                'status': m.get('status'),
                'blocking_reasons': [data_text(reason) for reason in m.get('blocking_reasons', [])[:5]],
            } for m in result],
            'truncated': len(machines) > limit,
            'incomplete': len(machines) > limit,
        })
    if name == 'get_rul_status':
        return {
            'available': False,
            'message': 'RUL non disponible pour cette machine : aucun modèle validé pour les machines SmartFactory.',
            'machine': data_text(args.get('machine_ref', '')),
            'truncated': False, 'incomplete': False,
        }
    raise ToolCallError('unknown_tool', 'Le modèle a demandé un outil non autorisé.')


def summarize_tool_result(name, result):
    if 'error' in result:
        return {'tool': name, 'error': result['error']}
    counts = {key: len(result[key]) for key in ('results', 'machines', 'alerts') if isinstance(result.get(key), list)}
    return {'tool': name, **counts, 'truncated': bool(result.get('truncated')), 'incomplete': bool(result.get('incomplete'))}
