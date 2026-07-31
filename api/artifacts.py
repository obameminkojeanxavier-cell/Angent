"""
Rendu public des artefacts sur /a/<slug>.

- text/html            -> rendu comme page (avec CSP pour limiter la casse)
- text/csv, json       -> téléchargement (Content-Disposition attachment)
- markdown, svg, plain -> affichage inline

Aucune authentification : l'URL longue et aléatoire (slug) sert de secret de
partage. Le contenu est produit par un agent ; à ne pas exposer de données
sensibles via un artefact public.
"""
import base64
import binascii

from django.http import HttpResponse, Http404

from .models import Artifact

_EXT = {
    'text/csv': 'csv',
    'application/json': 'json',
    'text/markdown': 'md',
    'image/svg+xml': 'svg',
    'text/plain': 'txt',
    'text/html': 'html',
    # Livrables binaires produits par les skills
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/zip': 'zip',
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
}

# Types téléchargés plutôt qu'affichés.
_DOWNLOAD = {
    'text/csv', 'application/json', 'application/zip',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

# Types affichés directement par le navigateur (inline).
_INLINE_BINARY = {'application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/gif'}

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

    # Nom de fichier lisible, avec l'extension correspondant au type réel.
    ext = _EXT.get(ct, 'txt')
    stem = (artifact.name or artifact.slug).rsplit('.', 1)[0] or artifact.slug
    filename = f'{stem}.{ext}'

    if artifact.is_binary:
        # Le contenu est stocké en base64 : on restitue les octets d'origine,
        # sinon le navigateur reçoit du texte base64 au lieu du fichier.
        try:
            data = base64.b64decode(artifact.content or '', validate=True)
        except (binascii.Error, ValueError):
            raise Http404("Artefact binaire illisible")
        resp = HttpResponse(data, content_type=ct)
        disposition = 'inline' if ct in _INLINE_BINARY else 'attachment'
        resp['Content-Disposition'] = f'{disposition}; filename="{filename}"'
        resp['X-Content-Type-Options'] = 'nosniff'
        return resp

    resp = HttpResponse(artifact.content, content_type=f'{ct}; charset=utf-8')
    resp['X-Content-Type-Options'] = 'nosniff'

    if ct == 'text/html':
        resp['Content-Security-Policy'] = _HTML_CSP
        resp['X-Frame-Options'] = 'SAMEORIGIN'
    elif ct in _DOWNLOAD:
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'

    return resp
