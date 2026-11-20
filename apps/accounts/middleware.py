"""Audit successful and rejected API mutations without retaining payloads."""
import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class ApiAuditMiddleware(MiddlewareMixin):
    """Record API writes (POST/PUT/PATCH/DELETE), including failed attempts.

    The request body is deliberately excluded because it may contain passwords,
    tokens, personal data, or uploaded file metadata.
    """

    METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

    def process_response(self, request, response):
        auditable_prefixes = ('/api/', '/admin/')
        if request.method not in self.METHODS or not request.path_info.startswith(auditable_prefixes):
            return response
        self._write(request, response.status_code)
        return response

    @staticmethod
    def _write(request, status_code):
        try:
            from .models import AuditLog

            user = getattr(request, 'user', None)
            authenticated = bool(user and getattr(user, 'is_authenticated', False))
            route = getattr(getattr(request, 'resolver_match', None), 'view_name', None)
            action = f'{request.method} {route or request.path_info}'
            AuditLog.objects.create(
                acteur=user if authenticated else None,
                acteur_email=getattr(user, 'email', '') if authenticated else '',
                acteur_role=getattr(user, 'role', '') if authenticated else '',
                action=action,
                methode=request.method,
                chemin=request.path_info[:512],
                code_http=status_code,
                adresse_ip=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
                details={'status_code': status_code},
            )
        except Exception:
            # Audit storage problems must not turn a valid business response into
            # a failed API response, but are reported for operational attention.
            logger.exception('Impossible de persister un événement du journal d’audit')
