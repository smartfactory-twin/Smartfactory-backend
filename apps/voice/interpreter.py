"""Interpréteur local borné aux données renvoyées par les API métier autorisées."""
import base64
import csv
import io
import re
import unicodedata
from datetime import timedelta
from xml.sax.saxutils import escape

from django.utils import timezone

from .tools import _call_api, execute_tool


def _normalize(text):
    decomposed = unicodedata.normalize('NFKD', str(text or '').casefold())
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def _plain(value):
    if isinstance(value, dict) and value.get('kind') == 'untrusted_data':
        return str(value.get('value') or '')
    return str(value or '')


class CommandInterpreter:
    """Repli déterministe : aucune requête ORM directe ni action d'écriture."""

    def __init__(self, user=None, request=None, conversation=None):
        self.user = user
        self.request = request
        self.conversation = conversation

    @staticmethod
    def is_export_request(text):
        normalized = _normalize(text)
        return bool(re.search(r'\b(csv|pdf|fichier|telecharge|export|rapport)\b', normalized))

    @staticmethod
    def is_machine_list_request(text):
        normalized = _normalize(text)
        mentions_machine = bool(re.search(r'\b(machine|machines)\b', normalized))
        asks_for_list = bool(re.search(r'\b(liste|lister|affiche|afficher|montre|montrer|donne|donner|quelles?|quels?)\b', normalized))
        asks_for_available = bool(re.search(r'\b(disponible|disponibles|visible|visibles)\b', normalized))
        return mentions_machine and (asks_for_list or asks_for_available)

    def _read(self, name, args=None):
        if self.request is None:
            return {'error': 'request_required'}
        return execute_tool(self.request, name, args or {})

    def _api_list(self, endpoint, params=None):
        payload, code = _call_api(self.request, 'GET', endpoint, params or {})
        if code >= 400:
            return [], 0, False, payload.get('error', 'api_error')
        if isinstance(payload, list):
            return payload, len(payload), False, None
        rows = payload.get('results', [])
        return rows if isinstance(rows, list) else [], payload.get('count', len(rows)), bool(payload.get('next')), None

    @staticmethod
    def _table(title, columns, rows, total=None, truncated=False):
        return {
            'title': title,
            'columns': [{'key': key, 'label': label} for key, label in columns],
            'rows': rows,
            'total': len(rows) if total is None else total,
            'truncated': bool(truncated),
        }

    def _result(self, intent, title, reply, columns, rows, total=None, truncated=False, tools=(), data=None):
        table = self._table(title, columns, rows, total, truncated)
        return {
            'intent': intent, 'response_text': reply, 'display_data': table,
            'data': data if data is not None else {'results': rows},
            'tools_called': list(tools), 'truncated': bool(truncated),
        }

    def _machines(self, normalized):
        raw, total, truncated, error = self._api_list('/api/equipements/machines/', {'page_size': 100})
        if error:
            return self._unavailable('machines')
        rows = [{
            'id': row.get('id'), 'nom': row.get('nom'),
            'identifiant': row.get('identifiant_interne'),
            'type': row.get('type_equipement'), 'statut': row.get('statut_label') or row.get('statut'),
            'usine': row.get('usine_nom'), 'zone': row.get('zone_nom'),
            'ligne': row.get('ligne_production_nom'),
        } for row in raw]
        marker = re.search(r'\b(?:dans|de|pour)\s+(?:l\s+)?(?:usine|zone|ligne|machine)\s+(.+?)(?:\?|$)', normalized)
        if marker:
            term = marker.group(1).strip(' .?!')
            matched = [row for row in rows if any(term in _normalize(row.get(key)) for key in ('usine', 'zone', 'ligne', 'nom', 'identifiant'))]
            rows = matched
            total = len(rows)
        kind = None
        for candidate in ('pompe', 'presse', 'compresseur', 'turbine', 'moteur', 'convoyeur'):
            if candidate in normalized and ('type' in normalized or 'types' in normalized):
                kind = candidate
                break
        if kind:
            rows = [row for row in rows if kind in _normalize(row.get('type')) or kind in _normalize(row.get('nom'))]
            total = len(rows)
        columns = [('nom', 'Machine'), ('identifiant', 'Identifiant'), ('type', 'Type'),
                   ('usine', 'Usine'), ('zone', 'Zone'), ('ligne', 'Ligne'), ('statut', 'Statut')]
        if 'combien' in normalized or 'nombre' in normalized:
            return {'intent': 'machine_count', 'response_text': f'{total} machine(s) visible(s) dans votre périmètre.',
                    'data': {'count': total}, 'tools_called': [], 'display_data': None}
        return self._result('machines', 'Machines', f'{total} machine(s) visible(s) dans votre périmètre.',
                            columns, rows, total, truncated, data={'results': rows, 'count': total})

    def _sensors(self, normalized):
        raw, total, truncated, error = self._api_list('/api/equipements/capteurs/', {'page_size': 100})
        if error:
            return self._unavailable('capteurs')
        sensors = [{
            'id': row.get('id'), 'nom': row.get('nom'), 'identifiant': row.get('identifiant'),
            'machine_id': row.get('machine'), 'machine': row.get('machine_nom') or row.get('machine_identifiant'),
            'type': row.get('type_capteur'), 'unite': row.get('unite'),
            'frequence': row.get('frequence_mesure'), 'seuil_min': row.get('seuil_min'),
            'seuil_max': row.get('seuil_max'),
        } for row in raw]
        machine_match = re.search(r'\b(?:dans|de|pour)\s+(?:la\s+)?([A-Z][A-Z0-9_-]{2,})\b', normalized, re.I)
        if machine_match:
            term = machine_match.group(1).casefold()
            sensors = [row for row in sensors if term in str(row['machine'] or '').casefold() or term in str(row['identifiant'] or '').casefold()]
            total = len(sensors)
        types = sorted({str(row['type']) for row in sensors if row['type']})
        if 'type' in normalized and ('combien' in normalized or 'types' in normalized):
            return {'intent': 'sensor_types', 'response_text': 'Types de capteurs visibles : ' + (', '.join(types) if types else 'aucun.'),
                    'data': {'types': types, 'count': len(types)}, 'tools_called': [], 'display_data': None}
        if re.search(r'\b(derniere|dernier|mesure|valeur)\b', normalized):
            candidates = [row for row in sensors if str(row['identifiant'] or '').casefold() in normalized or str(row['nom'] or '').casefold() in normalized]
            if len(candidates) == 1:
                reading = self._read('get_sensor_readings', {'sensor_id': candidates[0]['id'], 'limit': 1})
                values = reading.get('results', [])
                if values:
                    item = values[0]
                    value = item.get('value')
                    stamp = item.get('timestamp')
                    return {'intent': 'latest_reading', 'response_text': f"Dernière mesure de {candidates[0]['nom']} : {value} {candidates[0]['unite'] or ''}, le {stamp}.",
                            'data': reading, 'tools_called': ['get_sensor_readings'], 'display_data': None}
                return {'intent': 'latest_reading', 'response_text': f"Aucune mesure n’est enregistrée pour {candidates[0]['nom']}.", 'data': reading, 'tools_called': ['get_sensor_readings'], 'display_data': None}
            if not candidates:
                return {'intent': 'latest_reading', 'response_text': 'Précisez le nom ou l’identifiant du capteur pour retrouver sa dernière mesure.', 'data': {}, 'tools_called': [], 'display_data': None}
        columns = [('nom', 'Capteur'), ('identifiant', 'Identifiant'), ('machine', 'Machine'),
                   ('type', 'Type'), ('unite', 'Unité'), ('frequence', 'Fréquence (s)'),
                   ('seuil_min', 'Seuil min'), ('seuil_max', 'Seuil max')]
        if 'combien' in normalized or 'nombre' in normalized:
            return {'intent': 'sensor_count', 'response_text': f'{total} capteur(s) visible(s) dans votre périmètre.',
                    'data': {'count': total}, 'tools_called': [], 'display_data': None}
        return self._result('sensors', 'Capteurs', f'{total} capteur(s) visible(s) dans votre périmètre.',
                            columns, sensors, total, truncated, data={'results': sensors, 'count': total})

    def _alerts(self, normalized):
        params = {'page_size': 20, 'ordering': '-date_declenchement'}
        if re.search(r'\b(active|actives|ouvertes|ouverte|non resolue)\b', normalized):
            params['statut'] = 'ACTIVE'
        elif re.search(r'\b(acquittees|acquitte|acknowledged)\b', normalized):
            params['statut'] = 'ACKNOWLEDGED'
        elif re.search(r'\b(resolues|fermees|cloturees)\b', normalized):
            params['statut'] = 'RESOLVED'
        if 'critique' in normalized:
            params['niveau'] = 'CRITIQUE'
        now = timezone.localtime()
        if re.search(r'\b(aujourd hui|aujourdhui)\b', normalized):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            params['date_declenchement__gte'] = start.isoformat()
            params['date_declenchement__lte'] = (start + timedelta(days=1)).isoformat()
        elif re.search(r'\b(cette semaine|7 derniers jours|derniere semaine)\b', normalized):
            params['date_declenchement__gte'] = (now - timedelta(days=7)).isoformat()
            params['date_declenchement__lte'] = now.isoformat()
        elif re.search(r'\bce mois|ce mois-ci|dernier mois\b', normalized):
            params['date_declenchement__gte'] = (now - timedelta(days=30)).isoformat()
            params['date_declenchement__lte'] = now.isoformat()
        ref = re.search(r'\bAL-?(\d{1,8})\b', normalized, re.I)
        if ref:
            payload, code = _call_api(self.request, 'GET', f"/api/alertes/{int(ref.group(1))}/")
            if code >= 400:
                return {'intent': 'alert_detail', 'response_text': 'Cette alerte est introuvable ou hors de votre périmètre.', 'data': payload, 'tools_called': ['get_alert'], 'display_data': None}
            row = {
                'reference': payload.get('reference'), 'machine': payload.get('machine_nom'),
                'capteur': payload.get('capteur_identifiant'), 'niveau': payload.get('niveau_label'),
                'statut': payload.get('statut_label'), 'valeur': payload.get('derniere_valeur', payload.get('valeur')),
                'date': payload.get('date_declenchement'), 'acquitte_par': payload.get('acquittee_par_nom'),
                'commentaire': payload.get('commentaire_acquittement'),
            }
            reply = f"{row['reference']} : {row['niveau']}, {row['statut']}, {row['machine']}, valeur {row['valeur']}."
            if row['acquitte_par']:
                reply += f" Acquittée par {row['acquitte_par']}."
            return self._result('alert_detail', 'Alerte', reply,
                                [(key, label) for key, label in [('reference','Référence'),('machine','Machine'),('capteur','Capteur'),('niveau','Niveau'),('statut','Statut'),('valeur','Valeur'),('date','Date'),('acquitte_par','Acquittée par'),('commentaire','Commentaire')]],
                                [row], 1, False, ['get_alert'], payload)
        raw, total, truncated, error = self._api_list('/api/alertes/', params)
        if error:
            return self._unavailable('alertes')
        columns = [('reference', 'Référence'), ('machine', 'Machine'), ('capteur', 'Capteur'),
                   ('niveau', 'Niveau'), ('statut', 'Statut'), ('valeur', 'Valeur'),
                   ('date', 'Date'), ('acquitte_par', 'Acquittée par')]
        rows = [{
            'reference': row.get('reference'), 'machine': row.get('machine_nom'),
            'capteur': row.get('capteur_identifiant'), 'niveau': row.get('niveau_label') or row.get('niveau'),
            'statut': row.get('statut_label') or row.get('statut'), 'valeur': row.get('valeur'),
            'date': row.get('date_declenchement'), 'acquitte_par': row.get('acquittee_par_nom'),
        } for row in raw]
        count = total if not any(key.startswith('date_') for key in params) else len(rows)
        reply = f'{count} alerte(s) visible(s).' if rows else 'Aucune alerte correspondante dans votre périmètre.'
        if 'combien' in normalized or 'nombre' in normalized:
            return {'intent': 'alert_count', 'response_text': reply, 'data': {'count': count}, 'tools_called': ['list_alerts'], 'display_data': None}
        return self._result('alerts', 'Alertes', reply, columns, rows, count, truncated,
                            ['list_alerts'], {'results': rows, 'count': count})
    def _measurements(self, normalized):
        sensors, _, _, error = self._api_list('/api/equipements/capteurs/', {'page_size': 100})
        if error:
            return self._unavailable('mesures')
        terms = re.findall(r'\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b', normalized, re.I)
        candidates = [sensor for sensor in sensors if any(
            term.casefold() in str(sensor.get('identifiant') or '').casefold()
            or term.casefold() in str(sensor.get('nom') or '').casefold() for term in terms
        )]
        if not candidates:
            return {'intent': 'measurements', 'response_text': 'Précisez l’identifiant ou le nom du capteur pour consulter ses mesures.', 'data': {}, 'tools_called': [], 'display_data': None}
        if len(candidates) > 1:
            return {'intent': 'measurements', 'response_text': 'Plusieurs capteurs correspondent. Précisez un identifiant unique.', 'data': {}, 'tools_called': [], 'display_data': None}
        sensor = candidates[0]
        limit = 1 if re.search(r'\b(derniere|dernier|derniere valeur|derniere lecture)\b', normalized) else 50
        result = self._read('get_sensor_readings', {'sensor_id': sensor['id'], 'limit': limit})
        rows = result.get('results', [])
        columns = [('timestamp', 'Date'), ('value', f"Valeur ({sensor.get('unite') or ''})"), ('valid', 'Valide')]
        table_rows = [{'timestamp': row.get('timestamp'), 'value': row.get('value'), 'valid': row.get('valid')} for row in rows]
        return self._result('measurements', f"Mesures · {sensor.get('nom')}",
                            f"{len(rows)} mesure(s) retournée(s) pour {sensor.get('nom')}.",
                            columns, table_rows, result.get('count_returned', len(rows)),
                            result.get('truncated', False), ['get_sensor_readings'], result)
    def _work_orders(self, normalized):
        result = self._read('list_work_orders', {'limit': 20})
        rows = result.get('results', [])
        columns = [('title', 'Ordre de travail'), ('machine', 'Machine'), ('status', 'Statut'),
                   ('priority', 'Priorité'), ('assignee', 'Assigné à'), ('due_at', 'Échéance')]
        data_rows = [{key: _plain(row.get(key)) for key, _ in columns} for row in rows]
        count = result.get('count_returned', len(rows))
        reply = f'{count} ordre(s) de travail visible(s).' if rows else 'Aucun ordre de travail visible dans votre périmètre.'
        if result.get('error'):
            reply = 'Je n’ai pas pu lire les ordres de travail autorisés pour votre compte.'
        return self._result('work_orders', 'Ordres de travail', reply, columns, data_rows,
                            count, result.get('truncated', False), ['list_work_orders'], result)

    def _prediction(self, normalized):
        if re.search(r'\b(disponibilite ia|prete pour entrainement|readiness)\b', normalized):
            return self._readiness()
        if re.search(r'\b(rul|duree de vie restante)\b', normalized):
            reference = re.search(r'\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b', normalized, re.I)
            result = self._read('get_rul_status', {'machine_ref': reference.group(0) if reference else ''})
            return {'intent': 'rul', 'response_text': result.get('message', 'RUL non disponible pour cette machine.'),
                    'data': result, 'tools_called': ['get_rul_status']}
        if re.search(r'\b(what.if|what if|scenario|simulation|simule)\b', normalized):
            sensors, _, _, error = self._api_list('/api/equipements/capteurs/', {'page_size': 100})
            identifiers = re.findall(r'\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b', normalized, re.I)
            sensor = next((row for row in sensors if any(
                identifier.casefold() in str(row.get('identifiant') or '').casefold() for identifier in identifiers
            )), None)
            variation = re.search(r'(-?\d+(?:[.,]\d+)?)\s*%', normalized)
            if not sensor or not variation or error:
                return {'intent': 'what_if', 'response_text': 'Précisez l’identifiant du capteur et une variation en pourcentage, par exemple +20 %.', 'data': {}, 'tools_called': []}
            result = self._read('simulate_what_if', {
                'sensor_id': sensor['id'], 'variation_percent': float(variation.group(1).replace(',', '.')),
            })
            if result.get('error'):
                return {'intent': 'what_if', 'response_text': 'Le scénario n’a pas pu être calculé pour ce capteur.', 'data': result, 'tools_called': ['simulate_what_if']}
            return {'intent': 'what_if', 'response_text': f"Scénario calculé pour {sensor.get('nom')} avec une variation de {variation.group(1)} %. Aucune mesure réelle n’a été modifiée.", 'data': result, 'tools_called': ['simulate_what_if']}
        machines, _, _, error = self._api_list('/api/equipements/machines/', {'page_size': 100})
        identifiers = re.findall(r'\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b', normalized, re.I)
        match = next((machine for machine in machines if any(
            identifier.casefold() in str(machine.get('identifiant_interne') or '').casefold()
            or identifier.casefold() in str(machine.get('nom') or '').casefold() for identifier in identifiers
        )), None)
        if not match or error:
            return {'intent': 'anomaly', 'response_text': 'Précisez une machine visible pour consulter son score statistique d’anomalie.', 'data': {}, 'tools_called': []}
        result = self._read('get_anomaly_summary', {'machine_id': match['id']})
        if result.get('error'):
            return {'intent': 'anomaly', 'response_text': 'Le résumé d’anomalie est indisponible pour cette machine.', 'data': result, 'tools_called': ['get_anomaly_summary']}
        score = result.get('score')
        detected = result.get('detected')
        state = 'anomalie signalée' if detected else 'aucune anomalie au seuil configuré'
        answer = f"Pour {match.get('nom')}, le score statistique est {score if score is not None else 'non calculable'} ; {state}."
        return {'intent': 'anomaly', 'response_text': answer, 'data': result, 'tools_called': ['get_anomaly_summary']}
    def _readiness(self):
        result = self._read('get_model_availability', {'limit': 20})
        rows = result.get('machines', [])
        columns = [('machine', 'Machine'), ('eligible_sensor_count', 'Capteurs IA'),
                   ('valid_measure_count', 'Mesures valides'), ('history_days', 'Historique (jours)'),
                   ('missing_rate_percent', 'Valeurs manquantes (%)'), ('status', 'État')]
        data_rows = [{key: (_plain(row.get(key)) if key == 'machine' else row.get(key)) for key, _ in columns} for row in rows]
        reply = 'Disponibilité IA consultée pour les machines de votre périmètre.' if rows else 'Aucune disponibilité IA à afficher dans votre périmètre.'
        return self._result('readiness', 'Disponibilité IA', reply, columns, data_rows,
                            len(rows), result.get('truncated', False), ['get_model_availability'], result)

    def _export(self, normalized):
        if re.search(r'\b(mesure|mesures)\b', normalized) and re.search(r'\b(capteur|capteurs|sensor|sensors)\b', normalized):
            result = self._measurements(normalized)
        elif re.search(r'\b(capteur|capteurs|sensor|sensors)\b', normalized):
            result = self._sensors(normalized)
        elif re.search(r'\b(alerte|alertes|alarme|alarmes)\b', normalized):
            result = self._alerts(normalized)
        elif re.search(r'\b(ordre|ordres|maintenance|ot)\b', normalized):
            result = self._work_orders(normalized)
        elif re.search(r'\b(machine|machines|equipement|equipements)\b', normalized):
            result = self._machines(normalized)
        else:
            return {'intent': 'export', 'response_text': 'Précisez les données à exporter : machines, capteurs, mesures, alertes ou ordres de travail.', 'data': {}, 'tools_called': [], 'display_data': None}
        table = result.get('display_data')
        if not table:
            return result
        filename_base = result.get('intent', 'rapport')
        columns = table['columns']
        rows = table['rows']
        extension = 'pdf' if re.search(r'\bpdf\b', normalized) else 'csv'
        if extension == 'csv':
            buffer = io.StringIO(newline='')
            writer = csv.writer(buffer)
            writer.writerow([column['label'] for column in columns])
            for row in rows:
                writer.writerow([row.get(column['key'], '') for column in columns])
            content = buffer.getvalue().encode('utf-8-sig')
            content_type = 'text/csv; charset=utf-8'
        else:
            try:
                from reportlab.lib import colors
                from reportlab.lib.pagesizes import A4, landscape
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.units import mm
                from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
                output = io.BytesIO()
                document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=14*mm,
                                             leftMargin=14*mm, topMargin=15*mm, bottomMargin=15*mm)
                styles = getSampleStyleSheet()
                story = [Paragraph(escape(table['title']), styles['Title']),
                         Paragraph('SmartFactory Twin · export généré depuis les données visibles dans votre périmètre', styles['Normal']), Spacer(1, 8*mm)]
                body = [[Paragraph(escape(str(column['label'])), styles['BodyText']) for column in columns]]
                body.extend([[Paragraph(escape(str(row.get(column['key'], '') or '')), styles['BodyText']) for column in columns] for row in rows])
                grid = Table(body, repeatRows=1, hAlign='LEFT')
                grid.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#243b68')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#cbd5e1')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.extend([grid, Spacer(1, 4*mm), Paragraph(f"{table.get('total', len(rows))} résultat(s) · Généré le {timezone.localtime().strftime('%d/%m/%Y %H:%M')}", styles['Normal'])])
                document.build(story)
                content = output.getvalue()
                content_type = 'application/pdf'
            except Exception:
                return {'intent': 'export', 'response_text': 'La génération PDF est indisponible. Demandez un CSV ou réessayez plus tard.', 'data': {}, 'tools_called': [], 'display_data': table}
        file = {
            'filename': f"smartfactory_{filename_base}_{timezone.localtime():%Y%m%d}.{extension}",
            'content_type': content_type,
            'content_base64': base64.b64encode(content).decode('ascii'),
        }
        result['download'] = file
        result['response_text'] = f"Le fichier {file['filename']} est prêt. Utilisez le bouton de téléchargement pour l’enregistrer."
        return result

    def process(self, text):
        normalized = _normalize(text)
        if not normalized.strip():
            return self._unsupported()
        if re.search(r'\b(bonjour|salut|bonsoir|hello|coucou)\b', normalized):
            return {'intent': 'greeting', 'response_text': 'Bonjour. Je peux consulter les machines, alertes, capteurs, mesures, prédictions et ordres de travail.', 'tools_called': []}
        if re.search(r'\b(acquitte|acquitter|cree|creer|modifie|modifier|supprime|supprimer|annule|annuler)\b', normalized):
            return {'intent': 'write_unavailable', 'response_text': 'Le service conversationnel est indisponible. Je ne peux pas préparer cette action maintenant ; aucune modification n’a été effectuée. Réessayez plus tard.', 'tools_called': []}
        if self.is_export_request(normalized):
            return self._export(normalized)
        if re.search(r'\b(rul|duree de vie restante|prediction|predictions|anomalie|anomalies|what.if|what if|scenario|simulation|simule|disponibilite ia)\b', normalized):
            return self._prediction(normalized)
        if re.search(r'\b(alerte|alertes|alarme|alarmes)\b', normalized):
            if re.search(r'\b(par machine|repartition|classement)\b', normalized):
                now = timezone.localtime()
                start = now - timedelta(days=7 if 'semaine' in normalized else 30)
                result = self._read('get_alerts_by_machine', {
                    'date_debut': start.isoformat(), 'date_fin': now.isoformat(), 'limit': 50,
                })
                rows = result.get('results', [])
                columns = [('machine', 'Machine'), ('alert_count', 'Nombre d’alertes')]
                return self._result('alerts_by_machine', 'Alertes par machine',
                                    'Répartition des alertes sur la période demandée.', columns,
                                    [{key: (_plain(row.get(key)) if key == 'machine' else row.get(key)) for key, _ in columns} for row in rows],
                                    result.get('count', len(rows)), result.get('truncated', False),
                                    ['get_alerts_by_machine'], result)
            return self._alerts(normalized)
        if re.search(r'\b(mesure|mesures|derniere valeur|derniere lecture)\b', normalized) and re.search(r'\b(capteur|capteurs|sensor|sensors)\b', normalized):
            return self._measurements(normalized)
        if re.search(r'\b(capteur|capteurs|sensor|sensors)\b', normalized):
            return self._sensors(normalized)
        if re.search(r'\b(maintenance|ordres? de travail|interventions?|\bot\b)\b', normalized):
            return self._work_orders(normalized)
        if re.search(r'\b(machine|machines|equipement|equipements|usine|zone|ligne|combien|nombre)\b', normalized):
            return self._machines(normalized)
        if re.search(r'\b(prediction|predictions|anomalie|anomalies)\b', normalized):
            return self._readiness()
        return self._unsupported()

    @staticmethod
    def _unavailable(entity):
        return {'intent': entity, 'response_text': f"Je n’ai pas pu lire les {entity} autorisés pour votre compte.", 'data': {}, 'tools_called': []}

    @staticmethod
    def _unsupported():
        return {'intent': 'help', 'response_text': 'Le service conversationnel est indisponible. Le mode local peut consulter les machines, les alertes, les capteurs, les mesures, la disponibilité IA et les ordres de travail. Pour une demande plus complexe, réessayez quand le service IA sera disponible.', 'data': {}, 'tools_called': []}



