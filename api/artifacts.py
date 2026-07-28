"""
Rendu public des artefacts sur /a/<slug>.

- text/html            -> rendu comme page (avec CSP pour limiter la casse)
- text/csv, json       -> téléchargement (Content-Disposition attachment)
- markdown, svg, plain -> affichage inline

Aucune authentification : l'URL longue et aléatoire (slug) sert de secret de
partage. Le contenu est produit par un agent ; à ne pas exposer de données
sensibles via un artefact public.
"""
from django.http import HttpResponse, Http404

from .models import Artifact

_EXT = {
    'text/csv': 'csv',
    'application/json': 'json',
    'text/markdown': 'md',
    'image/svg+xml': 'svg',
    'text/plain': 'txt',
    'text/html': 'html',
}

# Types téléchargés plutôt qu'affichés.
_DOWNLOAD = {'text/csv', 'application/json'}

# CSP appliquée aux artefacts HTML : autorise le rendu (styles/scripts inline,
# images/polices en data:) mais empêche le chargement de ressources externes.
_HTML_CSP = (
    "default-src 'none'; "
    "img-src data: https:; "
    "style-src 'unsafe-inline'; "
    "font-src data:; "
    "script-src 'unsafe-inline'; "
    "form-action 'none'; "
    "base-uri 'none'"
)


def render_artifact(request, slug):
    try:
        artifact = Artifact.objects.get(slug=slug)
    except Artifact.DoesNotExist:
        raise Http404("Artefact introuvable")

    ct = artifact.content_type if artifact.content_type in _EXT else 'text/plain'
    resp = HttpResponse(artifact.content, content_type=f'{ct}; charset=utf-8')
    resp['X-Content-Type-Options'] = 'nosniff'

    if ct == 'text/html':
        resp['Content-Security-Policy'] = _HTML_CSP
        resp['X-Frame-Options'] = 'SAMEORIGIN'
    elif ct in _DOWNLOAD:
        filename = f'{artifact.slug}.{_EXT[ct]}'
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'

    return resp
