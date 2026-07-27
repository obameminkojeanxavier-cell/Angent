def client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def current_client(request):
    user = getattr(request, 'user', None)
    if user is not None and getattr(user, 'is_authenticated', False):
        return user
    return None


def audit(request, action, target='', status='success', detail=None):
    """Enregistre une opération dans le journal d'audit (best-effort)."""
    from .models import AuditLog
    client = current_client(request)
    try:
        AuditLog.objects.create(
            client=client if getattr(client, 'pk', None) else None,
            client_name=(client.name if client else 'anonymous'),
            action=action,
            target=target or '',
            status=status,
            detail=detail or {},
            ip=client_ip(request),
        )
    except Exception:
        # L'audit ne doit jamais casser une requête métier.
        pass
