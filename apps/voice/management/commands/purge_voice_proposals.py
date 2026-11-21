from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.voice.models import VoiceActionProposal


class Command(BaseCommand):
    help = 'Purge les anciennes propositions vocales déjà terminées ou expirées.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        days = max(1, options['days'])
        now = timezone.now()
        VoiceActionProposal.objects.filter(
            statut=VoiceActionProposal.Status.PENDING, expires_at__lte=now,
        ).update(statut=VoiceActionProposal.Status.EXPIRED, erreur='La proposition a expiré.')
        deleted, _ = VoiceActionProposal.objects.exclude(
            statut=VoiceActionProposal.Status.PENDING,
        ).filter(created_at__lt=now - timedelta(days=days)).delete()
        self.stdout.write(self.style.SUCCESS(f'{deleted} proposition(s) supprimée(s).'))
