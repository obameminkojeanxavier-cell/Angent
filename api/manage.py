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
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import render

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


def overview(request):
    if not _is_staff(request):
        return _forbidden()

    tables = []
    for t in DatabaseOperations.list_tables():
        try:
            rows = DatabaseOperations.count(t)
        except Exception:
            rows = None
        tables.append({'name': t, 'rows': rows})

    skills = [
        {'name': b['name'], 'description': b['description'], 'source': 'builtin', 'files': 0, 'is_active': True}
        for b in skills_registry._REGISTRY.values()
    ]
    for s in Skill.objects.all():
        skills.append({
            'name': s.name, 'description': s.description, 'source': 'db',
            'category': s.category, 'files': s.files.count(), 'is_active': s.is_active,
        })

    return JsonResponse({
        'tables': tables,
        'skills': skills,
        'agents': [_agent_dict(a) for a in AgentClient.objects.all()],
        'artifacts': Artifact.objects.count(),
        'audit': AuditLog.objects.count(),
        'all_scopes': ALL_SCOPES,
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
            'is_active': s.is_active,
            'files': [{'path': f.path, 'content_type': f.content_type, 'size': len(f.content or '')}
                      for f in s.files.all()],
        })
    return JsonResponse({'skills': data})


@require_POST
def skill_create(request):
    if not _is_staff(request):
        return _forbidden()
    body = json.loads(request.body or '{}')
    name = (body.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Nom requis'}, status=400)
    skill, _ = Skill.objects.update_or_create(
        name=name,
        defaults={
            'description': body.get('description', ''),
            'category': body.get('category', ''),
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
def skill_delete(request, name):
    if not _is_staff(request):
        return _forbidden()
    Skill.objects.filter(name=name).delete()
    return JsonResponse({'ok': True})
