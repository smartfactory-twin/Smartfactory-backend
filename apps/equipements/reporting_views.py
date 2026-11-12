from datetime import timedelta
from io import BytesIO

from django.db.models import Avg, Count, Max, Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alertes.models import Alerte
from .models import Machine, OrdreTravail, Reading
from .permissions import accessible_machine_ids, scope_queryset_machine


def _period(request):
    try:
        days = int(request.query_params.get('days', 30))
    except (TypeError, ValueError):
        days = 30
    if days not in (7, 30):
        return None, Response({'detail': 'La période acceptée est 7 ou 30 jours.'}, status=status.HTTP_400_BAD_REQUEST)
    return timezone.now() - timedelta(days=days), None


def _machine_health(machine, since):
    sensors = machine.capteurs.filter(actif=True).order_by('nom')
    sensor_rows = []
    total = 0
    in_range = 0
    for sensor in sensors:
        readings = Reading.objects.filter(
            sensor=sensor, timestamp__gte=since, est_valide=True,
        )
        stats = readings.aggregate(min=Min('valeur'), moy=Avg('valeur'), max=Max('valeur'), count=Count('id'))
        if not stats['count']:
            continue
        total += stats['count']
        in_range += readings.filter(valeur__gte=sensor.seuil_min, valeur__lte=sensor.seuil_max).count()
        sensor_rows.append({
            'nom': sensor.nom,
            'unite': sensor.unite,
            'min': stats['min'],
            'moy': stats['moy'],
            'max': stats['max'],
            'seuil_max': sensor.seuil_max,
            'mesures': stats['count'],
        })

    alert_count = Alerte.objects.filter(machine=machine, date_declenchement__gte=since).count()
    ot_count = OrdreTravail.objects.filter(machine=machine, created_at__gte=since).count()
    return {
        'sante': round(100 * in_range / total) if total else None,
        'rul': None,
        'statut': machine.statut,
        'alertes_count': alert_count,
        'ot_count': ot_count,
        'capteurs': sensor_rows,
        'nombre_mesures': total,
        'periode_debut': since,
        'periode_fin': timezone.now(),
    }


class MachineHealthReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        machine_id = request.query_params.get('machine_id')
        if not machine_id:
            return Response({'detail': 'Le paramètre machine_id est obligatoire.'}, status=status.HTTP_400_BAD_REQUEST)
        since, error = _period(request)
        if error:
            return error
        machine = get_object_or_404(
            scope_queryset_machine(Machine.objects.all(), request.user), pk=machine_id,
        )
        return Response(_machine_health(machine, since))


class ReportPdfAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        report_type = request.query_params.get('type')
        if report_type not in ('sante', 'anomalies', 'ot'):
            return Response({'detail': 'Type attendu : sante, anomalies ou ot.'}, status=status.HTTP_400_BAD_REQUEST)
        since, error = _period(request)
        if error:
            return error

        machine = None
        rows = []
        if report_type == 'sante':
            machine_id = request.query_params.get('machine_id')
            if not machine_id:
                return Response({'detail': 'Le paramètre machine_id est obligatoire pour un rapport santé.'}, status=status.HTTP_400_BAD_REQUEST)
            machine = get_object_or_404(scope_queryset_machine(Machine.objects.all(), request.user), pk=machine_id)
            health = _machine_health(machine, since)
            rows = [['Capteur', 'Mesures', 'Minimum', 'Moyenne', 'Maximum', 'Seuil max', 'Unité']]
            rows += [[r['nom'], r['mesures'], r['min'], r['moy'], r['max'], r['seuil_max'], r['unite']] for r in health['capteurs']]
            summary = f"État machine : {machine.get_statut_display()} | Indice mesures dans seuils : {health['sante'] if health['sante'] is not None else 'N/D'} % | Alertes : {health['alertes_count']} | OT : {health['ot_count']} | RUL : non calculée pour cette machine"
            title = f"Rapport de santé — {machine.nom}"
        elif report_type == 'anomalies':
            alerts = Alerte.objects.filter(
                machine_id__in=accessible_machine_ids(request.user), date_declenchement__gte=since,
            ).select_related('machine', 'capteur').order_by('-date_declenchement')[:2000]
            rows = [['Référence', 'Date', 'Machine', 'Capteur', 'Niveau', 'Statut', 'Message']]
            rows += [[a.reference or a.pk, timezone.localtime(a.date_declenchement).strftime('%d/%m/%Y %H:%M'), a.machine.nom, a.capteur.identifiant, a.get_niveau_display(), a.get_statut_display(), a.message] for a in alerts]
            summary = f'{len(rows) - 1} alerte(s) enregistrée(s) sur la période.'
            title = 'Rapport des alertes et anomalies'
        else:
            orders = OrdreTravail.objects.filter(
                machine_id__in=accessible_machine_ids(request.user), created_at__gte=since,
            ).select_related('machine').order_by('-created_at')[:2000]
            rows = [['OT', 'Date création', 'Machine', 'Type', 'Priorité', 'Statut', 'Durée (h)', 'Coût pièces']]
            total_parts = 0
            for order in orders:
                report = order.rapport or {}
                parts_cost = sum(float(p.get('qte', 0)) * float(p.get('cout', 0)) for p in report.get('pieces', []))
                total_parts += parts_cost
                rows.append([
                    order.pk, timezone.localtime(order.created_at).strftime('%d/%m/%Y %H:%M'),
                    order.machine.nom, order.type_ordre, order.priorite, order.statut,
                    report.get('duree', '—'), f'{parts_cost:.2f}',
                ])
            summary = f'{len(rows) - 1} OT | Coût des pièces déclaré : {total_parts:.2f} (unité du formulaire)'
            title = 'Récapitulatif des ordres de travail'

        return self._pdf_response(title, since, rows, summary, report_type)

    def _pdf_response(self, title, since, rows, summary, report_type):
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError:
            return Response(
                {'detail': 'La génération PDF nécessite ReportLab. Installe la dépendance avec « python -m pip install reportlab ». '},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        output = BytesIO()
        doc = SimpleDocTemplate(
            output, pagesize=landscape(A4), rightMargin=14 * mm,
            leftMargin=14 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
            title=title, author='SmartFactory Twin',
        )
        styles = getSampleStyleSheet()
        heading = ParagraphStyle('ReportHeading', parent=styles['Title'], alignment=TA_CENTER, textColor=colors.HexColor('#1D4ED8'))
        body = ParagraphStyle('ReportBody', parent=styles['BodyText'], fontSize=8, leading=10)
        story = [
            Paragraph('SmartFactory Twin', styles['Heading2']),
            Paragraph(title, heading),
            Paragraph(f"Période : {since.strftime('%d/%m/%Y %H:%M')} - {timezone.localtime().strftime('%d/%m/%Y %H:%M')}", styles['Normal']),
            Spacer(1, 5 * mm),
            Paragraph(summary, styles['Normal']),
            Spacer(1, 5 * mm),
        ]
        wrapped = [[Paragraph(str(cell).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), body) for cell in row] for row in rows]
        if len(wrapped) == 1:
            wrapped.append([Paragraph('Aucune donnée pour cette période.', body)] + [Paragraph('', body) for _ in rows[0][1:]])
        table = Table(wrapped, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A5F')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F1F5F9')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        doc.build(story)
        response = HttpResponse(output.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="smartfactory_{report_type}_{timezone.localdate().isoformat()}.pdf"'
        return response
