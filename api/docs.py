from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, Http404


def _serve_markdown(filename):
    path = Path(settings.BASE_DIR) / filename
    if not path.exists():
        raise Http404('Document introuvable')
    content = path.read_text(encoding='utf-8')
    resp = HttpResponse(content, content_type='text/markdown; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


def skill_doc(request):
    """Document d'intégration synthétique (datahub_skill.md)."""
    return _serve_markdown('datahub_skill.md')


def api_doc(request):
    """Documentation complète des API (API.md) — contrat d'intégration."""
    return _serve_markdown('API.md')
