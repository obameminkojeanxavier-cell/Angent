"""
Vues de la console d'exécution (interface GOD HAND).

- GET  /console/skills : liste des skills de document disponibles
- POST /console/run    : importe un document, l'exécute via un skill, renvoie
                         la trace complète (étapes, opérations base, résultat)
"""
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .tokens import resolve_client, master_client, SCOPE_SKILLS
from .documents import Tracer, run_document, list_doc_processors
from .models import SkillTask
from .audit import audit


def _principal(request):
    """
    Détermine l'identité exécutante :
    - token Bearer valide avec scope skills:trigger, sinon
    - console web autorisée (ALLOW_WEB_CONSOLE) -> compte master, sinon refus.
    Renvoie (client, erreur).
    """
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if header.startswith('Bearer '):
        client = resolve_client(header[len('Bearer '):].strip())
        if client is None:
            return None, 'invalid'
        if not client.has_scope(SCOPE_SKILLS):
            return None, 'forbidden'
        return client, None
    if getattr(settings, 'ALLOW_WEB_CONSOLE', False):
        return master_client(), None
    return None, 'forbidden'


def console_skills(request):
    return JsonResponse({'skills': list_doc_processors()})


@csrf_exempt
def console_run(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST requis'}, status=405)

    client, err = _principal(request)
    if err == 'invalid':
        return JsonResponse({'error': 'Token invalide'}, status=401)
    if err == 'forbidden' or client is None:
        return JsonResponse({'error': "Non autorisé (token skills:trigger requis, ou activer ALLOW_WEB_CONSOLE)"}, status=403)

    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({'error': 'Aucun fichier fourni (champ "file")'}, status=400)

    skill = request.POST.get('skill') or 'document.ingest'
    raw = upload.read()
    text = raw.decode('utf-8', errors='replace')
    doc = {
        'filename': upload.name,
        'size': upload.size,
        'text': text,
        'preview': text[:500],
    }

    tracer = Tracer()
    task = SkillTask.objects.create(
        client=client if getattr(client, 'pk', None) else None,
        skill=skill, params={'filename': upload.name, 'size': upload.size}, status='running',
    )
    try:
        result = run_document(skill, doc, client, tracer)
        task.status = 'succeeded'
        task.result = {'trace': tracer.steps, 'result': result}
        audit(request, 'document.run', skill, detail={'task': str(task.id), 'file': upload.name})
        payload = {'ok': True, 'skill': skill,
                   'document': {'filename': upload.name, 'size': upload.size},
                   'trace': tracer.steps, 'result': result, 'error': ''}
    except Exception as e:
        tracer.error(f"Erreur : {e}")
        task.status = 'failed'
        task.error = str(e)
        task.result = {'trace': tracer.steps}
        audit(request, 'document.run', skill, 'error', {'file': upload.name, 'error': str(e)})
        payload = {'ok': False, 'skill': skill,
                   'document': {'filename': upload.name, 'size': upload.size},
                   'trace': tracer.steps, 'result': None, 'error': str(e)}
    task.save()
    payload['task_id'] = str(task.id)
    return JsonResponse(payload)
