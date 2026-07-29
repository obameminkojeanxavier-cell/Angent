"""
Tableau de bord d'administration simple (GOD HAND).

Vue unique `/manage/` (réservée aux comptes staff, login Django) + endpoints
JSON `/manage/api/...` protégés par session : vue d'ensemble de la base,
gestion des droits par agent, gestion/import des skills.

Ces endpoints utilisent l'authentification par SESSION (pas les tokens API) :
seul un administrateur connecté peut les appeler.
"""
import json

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout as auth_logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
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
@staff_member_required
def dashboard(request):
    return render(request, 'dashboard.html', {'all_scopes': ALL_SCOPES})


def logout_view(request):
    """Déconnexion (GET ou POST) puis redirection vers la page de connexion admin."""
    auth_logout(request)
    return redirect('/admin/login/?loggedout=1')


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


def skills_list(request):
    if not _is_staff(request):
        return _forbidden()
    data = []
    for s in Skill.objects.all():
        data.append({
            'name': s.name, 'description': s.description, 'category': s.category,
            'kind': s.kind, 'is_orchestrator': s.is_orchestrator, 'is_active': s.is_active,
            'files': [{'path': f.path, 'content_type': f.content_type, 'size': len(f.content or '')}
                      for f in s.files.all()],
        })
    return JsonResponse({'skills': data, 'orchestrator_active': skills_registry.orchestrator_active()})


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
