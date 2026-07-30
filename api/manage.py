"""
Tableau de bord d'administration simple (GOD HAND).

Vue unique `/manage/` (réservée aux comptes staff, login Django) + endpoints
JSON `/manage/api/...` protégés par session : vue d'ensemble de la base,
gestion des droits par agent, gestion/import des skills.

Ces endpoints utilisent l'authentification par SESSION (pas les tokens API) :
seul un administrateur connecté peut les appeler.
"""
import json

from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.shortcuts import render, redirect

from .models import AgentClient, Skill, SkillFile, Artifact, AuditLog
from .db_operations import DatabaseOperations
from .tokens import generate_token, hash_token, ALL_SCOPES
from . import skills as skills_registry


def _is_staff(request):
    u = getattr(request, 'user', None)
    return bool(u and u.is_authenticated and u.is_staff)


def _forbidden():
    return JsonResponse({'error': 'Réservé aux administrateurs connectés'}, status=403)


def _agent_dict(a):
    return {
        'id': a.id, 'name': a.name, 'description': a.description,
        'scopes': a.scopes, 'allowed_tables': a.allowed_tables, 'is_active': a.is_active,
    }


@ensure_csrf_cookie
def dashboard(request):
    if not _is_staff(request):
        return redirect('/manage/login/?next=/manage/')
    return render(request, 'dashboard.html', {'all_scopes': ALL_SCOPES})


@ensure_csrf_cookie
def login_view(request):
    """Page de connexion à l'administration (GOD HAND), style maison."""
    nxt = request.GET.get('next') or request.POST.get('next') or '/manage/'
    if not str(nxt).startswith('/'):
        nxt = '/manage/'
    if _is_staff(request):
        return redirect(nxt)
    error = None
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username', ''),
            password=request.POST.get('password', ''),
        )
        if user is None:
            error = "Identifiants invalides."
        elif not user.is_staff:
            error = "Ce compte n'a pas accès à l'administration."
        else:
            auth_login(request, user)
            return redirect(nxt)
    return render(request, 'login.html', {'error': error, 'next': nxt})


def logout_view(request):
    """Déconnexion puis retour à la page de connexion GOD HAND."""
    auth_logout(request)
    return redirect('/manage/login/?loggedout=1')


def _skill_catalog(active_only=False):
    """Catalogue des skills : natifs + base."""
    items = [
        {'name': b['name'], 'description': b['description'], 'category': 'builtin',
         'source': 'builtin', 'is_active': True, 'files': 0}
        for b in skills_registry._REGISTRY.values()
    ]
    try:
        qs = Skill.objects.all()
        if active_only:
            qs = qs.filter(is_active=True)
        for s in qs:
            items.append({
                'name': s.name, 'description': s.description, 'category': s.category or 'db',
                'source': 'db', 'is_active': s.is_active, 'files': s.files.count(),
                'updated_at': s.updated_at.isoformat(),
            })
    except Exception:
        pass
    return items


def public_skills(request):
    """Catalogue PUBLIC (sans auth) des skills actifs, pour la page d'accueil."""
    return JsonResponse({'skills': _skill_catalog(active_only=True)})


def overview(request):
    if not _is_staff(request):
        return _forbidden()

    # Chaque section est protégée : une erreur (ex: migration manquante) ne doit
    # pas vider tout le tableau de bord.
    tables = []
    try:
        for t in DatabaseOperations.list_tables():
            try:
                rows = DatabaseOperations.count(t)
            except Exception:
                rows = None
            tables.append({'name': t, 'rows': rows})
    except Exception:
        pass

    skills = _skill_catalog()
    try:
        agents = [_agent_dict(a) for a in AgentClient.objects.all()]
    except Exception:
        agents = []
    try:
        artifacts = Artifact.objects.count()
    except Exception:
        artifacts = 0
    try:
        audit = AuditLog.objects.count()
    except Exception:
        audit = 0

    active_skills = sum(1 for s in skills if s.get('is_active'))
    return JsonResponse({
        'tables': tables,
        'skills': skills,
        'agents': agents,
        'artifacts': artifacts,
        'audit': audit,
        'all_scopes': ALL_SCOPES,
        'stats': {
            'tables': len(tables),
            'skills_total': len(skills),
            'skills_active': active_skills,
            'skills_inactive': len(skills) - active_skills,
            'agents_total': len(agents),
            'agents_active': sum(1 for a in agents if a.get('is_active')),
            'artifacts': artifacts,
            'audit': audit,
        },
    })


@require_POST
def agent_create(request):
    if not _is_staff(request):
        return _forbidden()
    body = json.loads(request.body or '{}')
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Nom requis'}, status=400)
    if AgentClient.objects.filter(name=name).exists():
        return JsonResponse({'error': 'Nom déjà utilisé'}, status=400)
    token = generate_token()
    AgentClient.objects.create(
        name=name, description=body.get('description', ''),
        token_hash=hash_token(token),
        scopes=body.get('scopes') or [],
        allowed_tables=body.get('allowed_tables') or [],
    )
    # Le token en clair n'est renvoyé qu'ici, une seule fois.
    return JsonResponse({'ok': True, 'name': name, 'token': token})


@require_POST
def agent_update(request, agent_id):
    if not _is_staff(request):
        return _forbidden()
    try:
        a = AgentClient.objects.get(pk=agent_id)
    except AgentClient.DoesNotExist:
        return JsonResponse({'error': 'Agent introuvable'}, status=404)
    body = json.loads(request.body or '{}')
    if 'scopes' in body:
        a.scopes = body['scopes']
    if 'allowed_tables' in body:
        a.allowed_tables = body['allowed_tables']
    if 'is_active' in body:
        a.is_active = bool(body['is_active'])
    a.save()
    return JsonResponse({'ok': True, 'agent': _agent_dict(a)})


@require_POST
def agent_delete(request, agent_id):
    if not _is_staff(request):
        return _forbidden()
    AgentClient.objects.filter(pk=agent_id).delete()
    return JsonResponse({'ok': True})


@csrf_exempt
@require_GET
def skills_list(request):
    """Endpoint pour lister les skills disponibles (accessible sans authentification pour les agents)."""
    data = []
    for s in Skill.objects.all():
        data.append({
            'name': s.name, 'description': s.description, 'category': s.category,
            'kind': s.kind, 'is_orchestrator': s.is_orchestrator, 'is_active': s.is_active,
            'updated_at': s.updated_at.isoformat() if s.updated_at else None,
            'files': [{'path': f.path, 'content_type': f.content_type, 'size': len(f.content or '')}
                      for f in s.files.all()],
        })
    return JsonResponse({'skills': data, 'orchestrator_active': skills_registry.orchestrator_active()})


skills_list.csrf_exempt = True


@csrf_exempt
@require_GET
def orchestrator_active(request):
    """Endpoint dédié pour récupérer l'orchestrateur actif.
    
    Retourne les détails de l'orchestrateur actif ou null si aucun n'est disponible.
    Accessible sans authentification (pour les agents).
    """
    try:
        orchestrator = Skill.objects.filter(is_orchestrator=True, is_active=True).first()
        if not orchestrator:
            return JsonResponse({'orchestrator': None, 'message': 'Aucun orchestrateur actif'})
        
        return JsonResponse({
            'orchestrator': {
                'name': orchestrator.name,
                'description': orchestrator.description,
                'category': orchestrator.category,
                'kind': orchestrator.kind,
                'is_active': orchestrator.is_active,
                'updated_at': orchestrator.updated_at.isoformat() if orchestrator.updated_at else None,
                'origin': 'imported',  # Peut être étendu pour 'default' plus tard
                'files': [
                    {'path': f.path, 'content_type': f.content_type, 'size': len(f.content or '')}
                    for f in orchestrator.files.all()
                ],
                'instructions': orchestrator.entry_instructions,
            },
            'message': 'Orchestrateur actif disponible'
        })
    except Exception as e:
        return JsonResponse({'orchestrator': None, 'message': f'Erreur: {str(e)}'}, status=500)


orchestrator_active.csrf_exempt = True


@require_POST
def skill_create(request):
    if not _is_staff(request):
        return _forbidden()
    body = json.loads(request.body or '{}')
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Nom requis'}, status=400)
    is_orch = bool(body.get('is_orchestrator'))
    skill, _ = Skill.objects.update_or_create(
        name=name,
        defaults={
            'description': body.get('description', ''),
            'category': body.get('category', ''),
            'kind': ('orchestrateur' if is_orch else body.get('kind', '')),
            'is_orchestrator': is_orch,
            'instructions': body.get('instructions', ''),
            'is_active': True,
        },
    )
    # Fichiers fournis (dossier)
    for f in (body.get('files') or []):
        p = (f.get('path') or '').strip()
        if not p:
            continue
        SkillFile.objects.update_or_create(
            skill=skill, path=p,
            defaults={'content': f.get('content', ''), 'content_type': f.get('content_type', 'text/plain')},
        )
    # Si des instructions sont données sans SKILL.md, on en crée un.
    instr = body.get('instructions')
    if instr and not skill.files.filter(path__iexact='SKILL.md').exists():
        SkillFile.objects.create(skill=skill, path='SKILL.md', content=instr, content_type='text/markdown')
    return JsonResponse({'ok': True, 'name': name})


_CT_BY_EXT = {
    '.md': 'text/markdown', '.markdown': 'text/markdown', '.html': 'text/html', '.htm': 'text/html',
    '.txt': 'text/plain', '.json': 'application/json', '.csv': 'text/csv',
    '.py': 'text/x-python', '.js': 'text/javascript', '.css': 'text/css',
    '.svg': 'image/svg+xml', '.yaml': 'text/yaml', '.yml': 'text/yaml',
}
_MAX_IMPORT_FILE = 1_000_000


def _clean_zip_path(p):
    p = p.replace('\\', '/').lstrip('/')
    parts = [x for x in p.split('/') if x not in ('', '.', '..')]
    return '/'.join(parts)


@require_POST
def skill_import(request):
    """Importe un skill depuis un fichier .md OU un .zip (dossier complet)."""
    if not _is_staff(request):
        return _forbidden()
    import io
    import os
    import zipfile

    up = request.FILES.get('file')
    if not up:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)
    name = (request.POST.get('name') or '').strip()
    is_orch = str(request.POST.get('is_orchestrator', '')).lower() in ('1', 'true', 'on', 'yes')
    description = request.POST.get('description', '')
    category = request.POST.get('category', '')
    fname = up.name or 'skill'

    files = []  # (path, content)
    if fname.lower().endswith('.zip'):
        try:
            z = zipfile.ZipFile(io.BytesIO(up.read()))
        except zipfile.BadZipFile:
            return JsonResponse({'error': 'Fichier ZIP invalide'}, status=400)
        for member in z.namelist():
            if member.endswith('/'):
                continue
            cp = _clean_zip_path(member)
            if not cp:
                continue
            try:
                data = z.read(member)
                content = data.decode('utf-8')
            except Exception:
                continue  # binaire / illisible : ignoré
            if len(content.encode('utf-8')) > _MAX_IMPORT_FILE:
                continue
            files.append((cp, content))
        # Retire un dossier racine commun (ex: "mon_skill/SKILL.md" -> "SKILL.md")
        tops = {p.split('/')[0] for p, _ in files if '/' in p}
        if files and len(tops) == 1 and all('/' in p for p, _ in files):
            root = tops.pop()
            files = [(p[len(root) + 1:], c) for p, c in files]
        if not name:
            name = _clean_zip_path(fname)[:-4] or 'skill'
    else:
        content = up.read().decode('utf-8', errors='replace')
        path = 'SKILL.md' if fname.lower().endswith(('.md', '.markdown')) else fname
        files = [(path, content)]
        if not name:
            name = fname.rsplit('.', 1)[0]

    if not name:
        return JsonResponse({'error': 'Nom requis'}, status=400)
    if not files:
        return JsonResponse({'error': 'Aucun fichier texte exploitable dans l\'archive'}, status=400)

    skill, _ = Skill.objects.update_or_create(
        name=name,
        defaults={
            'description': description, 'category': category,
            'kind': ('orchestrateur' if is_orch else category),
            'is_orchestrator': is_orch, 'is_active': True,
        },
    )
    skill.files.all().delete()
    for p, c in files:
        ext = os.path.splitext(p)[1].lower()
        SkillFile.objects.create(skill=skill, path=p, content=c,
                                 content_type=_CT_BY_EXT.get(ext, 'text/plain'))
    return JsonResponse({'ok': True, 'name': name, 'is_orchestrator': is_orch,
                         'files': [p for p, _ in files]})


def skill_detail(request, name):
    if not _is_staff(request):
        return _forbidden()
    try:
        s = Skill.objects.get(name=name)
    except Skill.DoesNotExist:
        return JsonResponse({'error': 'Skill introuvable'}, status=404)
    return JsonResponse({
        'name': s.name, 'description': s.description, 'category': s.category,
        'kind': s.kind, 'is_orchestrator': s.is_orchestrator, 'is_active': s.is_active,
        'instructions': s.entry_instructions,
        'files': [{'path': f.path, 'content_type': f.content_type, 'content': f.content}
                  for f in s.files.all()],
    })


@require_POST
def skill_toggle(request, name):
    if not _is_staff(request):
        return _forbidden()
    try:
        s = Skill.objects.get(name=name)
    except Skill.DoesNotExist:
        return JsonResponse({'error': 'Skill introuvable'}, status=404)
    s.is_active = not s.is_active
    s.save()
    return JsonResponse({'ok': True, 'is_active': s.is_active})


@require_POST
def skill_delete(request, name):
    if not _is_staff(request):
        return _forbidden()
    Skill.objects.filter(name=name).delete()
    return JsonResponse({'ok': True})
