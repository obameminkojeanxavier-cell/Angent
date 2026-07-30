import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
from django.core.exceptions import ValidationError
from django.conf import settings

from .authentication import AgentTokenAuthentication
from .permissions import ReadAccess, HasScope, OrchestratorGate
from .db_operations import DatabaseOperations
from .audit import audit
from .tokens import (
    SCOPE_DATA_READ, SCOPE_DATA_WRITE, SCOPE_TABLES, SCOPE_SKILLS, SCOPE_AUDIT,
)
from . import skills as skills_registry
from .models import SkillTask, AuditLog, Artifact


# --- Bases ------------------------------------------------------------------

class ReadView(APIView):
    """Lecture : token optionnel (selon REQUIRE_AUTH_FOR_READ) + scope data:read si authentifié."""
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [ReadAccess, OrchestratorGate]
    orchestrator_exempt = False


class ScopedView(APIView):
    """Opération protégée : token obligatoire + `required_scope` + verrou orchestrateur."""
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [HasScope, OrchestratorGate]
    required_scope = None
    orchestrator_exempt = False


def _check_table(request, table):
    """Refuse l'accès si le client a une liste de tables et que `table` n'y est pas."""
    user = request.user
    if getattr(user, 'is_authenticated', False) and not user.can_access_table(table):
        raise PermissionDenied(f"Table non autorisée pour ce client : {table}")


def _task_dict(task):
    return {
        'id': str(task.id),
        'skill': task.skill,
        'status': task.status,
        'params': task.params,
        'result': task.result,
        'error': task.error,
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
    }


# --- Données : lecture ------------------------------------------------------

class ListTablesView(ScopedView):
    """Liste des tables nécessite une authentification obligatoire."""
    required_scope = SCOPE_DATA_READ
    orchestrator_exempt = False

    def get(self, request):
        try:
            tables = DatabaseOperations.list_tables()
            audit(request, 'list_tables')
            return Response({'tables': tables}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TableSchemaView(ReadView):
    def get(self, request):
        table_name = request.query_params.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _check_table(request, table_name)
            schema = DatabaseOperations.get_table_schema(table_name)
            audit(request, 'schema', table_name)
            return Response({'schema': schema}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SelectView(ReadView):
    def get(self, request):
        table_name = request.query_params.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _check_table(request, table_name)
            filters = request.query_params.dict()
            filters.pop('table_name', None)
            limit = filters.pop('limit', None)
            results = DatabaseOperations.select(table_name, filters, limit)
            audit(request, 'select', table_name, detail={'rows': len(results)})
            return Response({'data': results}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SearchView(ReadView):
    def get(self, request):
        table_name = request.query_params.get('table_name')
        q = request.query_params.get('q', '')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        columns = request.query_params.get('columns')
        columns = [c.strip() for c in columns.split(',')] if columns else None
        limit = request.query_params.get('limit')
        try:
            _check_table(request, table_name)
            results = DatabaseOperations.search(table_name, q, columns, limit)
            audit(request, 'search', table_name, detail={'q': q, 'rows': len(results)})
            return Response({'count': len(results), 'data': results}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- Données : écriture -----------------------------------------------------

class CreateTableView(ScopedView):
    required_scope = SCOPE_TABLES

    def post(self, request):
        table_name = request.data.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            columns = _coerce_obj(request.data.get('columns'), 'columns')
            if not columns:
                return Response({'error': 'columns is required'}, status=status.HTTP_400_BAD_REQUEST)
            _check_table(request, table_name)
            DatabaseOperations.create_table(table_name, columns)
            audit(request, 'create_table', table_name, detail={'columns': list(columns)})
            return Response({'message': f'Table {table_name} created successfully'}, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            audit(request, 'create_table', table_name, 'error', {'error': str(e)})
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            audit(request, 'create_table', table_name, 'error', {'error': str(e)})
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddColumnView(ScopedView):
    required_scope = SCOPE_TABLES

    def post(self, request):
        table_name = request.data.get('table_name')
        column_name = request.data.get('column_name')
        column_type = request.data.get('column_type')
        if not all([table_name, column_name, column_type]):
            return Response({'error': 'table_name, column_name, and column_type are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            _check_table(request, table_name)
            DatabaseOperations.add_column(table_name, column_name, column_type)
            audit(request, 'add_column', table_name, detail={'column': column_name})
            return Response({'message': f'Column {column_name} added to {table_name}'}, status=status.HTTP_200_OK)
        except ValidationError as e:
            audit(request, 'add_column', table_name, 'error', {'error': str(e)})
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            audit(request, 'add_column', table_name, 'error', {'error': str(e)})
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InsertView(ScopedView):
    required_scope = SCOPE_DATA_WRITE

    def post(self, request):
        table_name = request.data.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = _coerce_obj(request.data.get('data'), 'data')
            if not data:
                return Response({'error': 'data is required'}, status=status.HTTP_400_BAD_REQUEST)
            _check_table(request, table_name)
            record = DatabaseOperations.insert(table_name, data)
            row_id = record.get('id') if isinstance(record, dict) else record
            audit(request, 'insert', table_name, detail={'id': row_id})
            return Response(
                {'message': 'Data inserted successfully', 'id': row_id, 'record': record},
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as e:
            audit(request, 'insert', table_name, 'error', {'error': str(e)})
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            audit(request, 'insert', table_name, 'error', {'error': str(e)})
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateView(ScopedView):
    required_scope = SCOPE_DATA_WRITE

    def put(self, request):
        table_name = request.data.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = _coerce_obj(request.data.get('data'), 'data')
            filters = _coerce_obj(request.data.get('filters'), 'filters')
            if not data:
                return Response({'error': 'data is required'}, status=status.HTTP_400_BAD_REQUEST)
            if not filters:
                return Response({'error': 'filters is required for safety'}, status=status.HTTP_400_BAD_REQUEST)
            _check_table(request, table_name)
            row_count = DatabaseOperations.update(table_name, data, filters)
            audit(request, 'update', table_name, detail={'rows': row_count})
            return Response({'message': f'{row_count} row(s) updated'}, status=status.HTTP_200_OK)
        except ValidationError as e:
            audit(request, 'update', table_name, 'error', {'error': str(e)})
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            audit(request, 'update', table_name, 'error', {'error': str(e)})
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteView(ScopedView):
    required_scope = SCOPE_DATA_WRITE

    def delete(self, request):
        table_name = request.data.get('table_name')
        if not table_name:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            filters = _coerce_obj(request.data.get('filters'), 'filters')
            if not filters:
                return Response({'error': 'filters is required for safety'}, status=status.HTTP_400_BAD_REQUEST)
            _check_table(request, table_name)
            row_count = DatabaseOperations.delete(table_name, filters)
            audit(request, 'delete', table_name, detail={'rows': row_count})
            return Response({'message': f'{row_count} row(s) deleted'}, status=status.HTTP_200_OK)
        except ValidationError as e:
            audit(request, 'delete', table_name, 'error', {'error': str(e)})
            return _bad(e)
        except PermissionDenied:
            raise
        except Exception as e:
            audit(request, 'delete', table_name, 'error', {'error': str(e)})
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- Skills & tâches --------------------------------------------------------

class SkillsListView(ReadView):
    """Liste des skills accessible sans authentification obligatoire (pour ChatGPT)."""
    orchestrator_exempt = True  # catalogue toujours consultable

    def get(self, request):
        return Response({
            'skills': skills_registry.list_skills(),
            'orchestrator_active': skills_registry.orchestrator_active(),
        }, status=status.HTTP_200_OK)


class SkillDefinitionView(ReadView):
    """Définition complète d'un skill : l'agent la lit pour savoir l'utiliser."""
    orchestrator_exempt = True

    def get(self, request, name):
        definition = skills_registry.get_definition(name)
        if not definition:
            raise NotFound(f"Skill inconnu : {name}")
        audit(request, 'skill.read', name)
        return Response(definition, status=status.HTTP_200_OK)


class SkillFileView(ReadView):
    """Lire un fichier d'un skill (skill = dossier de fichiers)."""
    orchestrator_exempt = True

    def get(self, request, name, filepath):
        f = skills_registry.get_skill_file(name, filepath)
        if not f:
            raise NotFound(f"Fichier introuvable : {name}/{filepath}")
        audit(request, 'skill.file', f"{name}/{filepath}")
        return Response(f, status=status.HTTP_200_OK)


class SkillRunView(ReadView):
    orchestrator_exempt = True

    def post(self, request, name):
        skill = skills_registry.get_skill(name)
        client = request.user
        try:
            params = _coerce_obj(request.data.get('params'), 'params')
        except ValidationError as e:
            return _bad(e)
        
        if not skill:
            # Skill de base de données : essayer de l'exécuter comme template
            definition = skills_registry.get_definition(name)
            if not definition:
                raise NotFound(f"Skill inconnu : {name}")
            
            # Si le skill est de la base de données, essayer de générer un artefact
            if definition.get('source') == 'db':
                task = SkillTask.objects.create(
                    client=client if getattr(client, 'pk', None) else None,
                    skill=name, params=params, status='running',
                )
                try:
                    # Générer le contenu en utilisant les fichiers du skill
                    from .models import Skill, SkillFile
                    skill_obj = Skill.objects.get(name=name, is_active=True)
                    
                    # Chercher un fichier template principal (ex: template.html, template.md)
                    template_file = skill_obj.files.filter(
                        path__icontains='template'
                    ).first()
                    
                    if not template_file:
                        # Sinon, prendre le premier fichier non-MD
                        template_file = skill_obj.files.filter(
                            path__iendswith='.html'
                        ).first()
                    
                    if not template_file:
                        # Sinon, prendre SKILL.md
                        template_file = skill_obj.files.filter(
                            path__iexact='SKILL.md'
                        ).first()
                    
                    if template_file:
                        content = template_file.content
                        # Remplacer les paramètres dans le template
                        for key, value in params.items():
                            content = content.replace(f'{{{key}}}', str(value))
                        
                        # Créer un artefact avec le contenu généré
                        from .models import Artifact
                        artifact = Artifact.objects.create(
                            name=f"{name}_output",
                            content_type=template_file.content_type,
                            content=content,
                            client=client if getattr(client, 'pk', None) else None,
                        )
                        
                        # Générer l'URL publique
                        base = getattr(settings, 'OPENAPI_BASE_URL', '') or f"{request.scheme}://{request.get_host()}"
                        url = f"{base}/a/{artifact.slug}"
                        
                        task.status = 'succeeded'
                        task.result = {
                            'artifact': artifact.slug,
                            'url': url,
                            'content_type': artifact.content_type,
                        }
                        audit(request, 'skill.run', name, detail={'task': str(task.id)})
                    else:
                        task.status = 'failed'
                        task.error = "Aucun fichier template trouvé dans le skill"
                        audit(request, 'skill.run', name, 'error', {'task': str(task.id), 'error': task.error})
                except Exception as e:
                    task.status = 'failed'
                    task.error = str(e)
                    audit(request, 'skill.run', name, 'error', {'task': str(task.id), 'error': str(e)})
                task.save()
                return Response(_task_dict(task), status=status.HTTP_200_OK)
            
            # Skill instructionnel : renvoyer les instructions
            audit(request, 'skill.read', name)
            return Response({
                'skill': name,
                'type': 'instructions',
                'instructions': definition['instructions'],
                'input_example': definition['input_example'],
                'note': "Ce skill est instructionnel : suis ces instructions en "
                        "appelant les actions (selectData, insertData, updateData, ...).",
            }, status=status.HTTP_200_OK)

        task = SkillTask.objects.create(
            client=client if getattr(client, 'pk', None) else None,
            skill=name, params=params, status='running',
        )
        try:
            result = skill['fn'](params, client)
            task.status = 'succeeded'
            task.result = result
            audit(request, 'skill.run', name, detail={'task': str(task.id)})
        except Exception as e:
            task.status = 'failed'
            task.error = str(e)
            audit(request, 'skill.run', name, 'error', {'task': str(task.id), 'error': str(e)})
        task.save()
        return Response(_task_dict(task), status=status.HTTP_200_OK)


class TaskDetailView(ScopedView):
    required_scope = SCOPE_SKILLS

    def get(self, request, task_id):
        task = _get_owned_task(request, task_id)
        return Response(_task_dict(task), status=status.HTTP_200_OK)


class TaskResultView(ScopedView):
    """Permet à un agent externe de renvoyer le résultat d'une tâche (async)."""
    required_scope = SCOPE_SKILLS

    def post(self, request, task_id):
        task = _get_owned_task(request, task_id)
        new_status = request.data.get('status', 'succeeded')
        if new_status not in ('succeeded', 'failed', 'running'):
            return Response({'error': "status must be succeeded|failed|running"}, status=status.HTTP_400_BAD_REQUEST)
        task.status = new_status
        if 'result' in request.data:
            task.result = request.data.get('result')
        if 'error' in request.data:
            task.error = request.data.get('error') or ''
        task.save()
        audit(request, 'task.result', task.skill, detail={'task': str(task.id), 'status': new_status})
        return Response(_task_dict(task), status=status.HTTP_200_OK)


def _get_owned_task(request, task_id):
    try:
        task = SkillTask.objects.get(pk=task_id)
    except SkillTask.DoesNotExist:
        raise NotFound("Tâche introuvable")
    user = request.user
    # Un client ne voit que ses propres tâches, sauf le master (scope '*').
    if not user.has_scope('*') and task.client_id and getattr(user, 'pk', None) and task.client_id != user.pk:
        raise PermissionDenied("Cette tâche appartient à un autre client.")
    return task


# --- Artefacts (fichiers produits) ------------------------------------------

# Types de contenu autorisés pour un artefact.
ARTIFACT_CONTENT_TYPES = {
    'text/html', 'text/plain', 'text/csv', 'application/json',
    'text/markdown', 'image/svg+xml',
}


def _artifact_url(request, slug):
    base = getattr(settings, 'OPENAPI_BASE_URL', '') or f"{request.scheme}://{request.get_host()}"
    return f"{base}/a/{slug}"


class ArtifactCreateView(ReadView):
    """Créer un artefact (contenu produit par l'agent). Renvoie son URL publique."""
    orchestrator_exempt = True

    def post(self, request):
        name = request.data.get('name', '')
        content = request.data.get('content')
        content_type = (request.data.get('content_type') or 'text/html').lower().strip()
        if content is None or content == '':
            return Response({'error': 'content is required'}, status=status.HTTP_400_BAD_REQUEST)
        if content_type not in ARTIFACT_CONTENT_TYPES:
            return Response(
                {'error': f"content_type invalide. Autorisés : {sorted(ARTIFACT_CONTENT_TYPES)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        client = request.user
        artifact = Artifact.objects.create(
            name=name or '', content_type=content_type, content=str(content),
            client=client if getattr(client, 'pk', None) else None,
        )
        url = _artifact_url(request, artifact.slug)
        audit(request, 'artifact.create', artifact.slug, detail={'content_type': content_type, 'name': name})
        return Response(
            {'slug': artifact.slug, 'url': url, 'name': artifact.name, 'content_type': content_type},
            status=status.HTTP_201_CREATED,
        )


class ArtifactListView(ScopedView):
    required_scope = SCOPE_DATA_READ

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 50))
        except (ValueError, TypeError):
            limit = 50
        limit = max(1, min(limit, 500))
        items = Artifact.objects.all()[:limit]
        data = [{
            'slug': a.slug, 'name': a.name, 'content_type': a.content_type,
            'url': _artifact_url(request, a.slug), 'created_at': a.created_at.isoformat(),
        } for a in items]
        return Response({'count': len(data), 'artifacts': data}, status=status.HTTP_200_OK)


class ArtifactDetailView(ScopedView):
    required_scope = SCOPE_DATA_READ

    def get(self, request, slug):
        try:
            a = Artifact.objects.get(slug=slug)
        except Artifact.DoesNotExist:
            raise NotFound("Artefact introuvable")
        return Response({
            'slug': a.slug, 'name': a.name, 'content_type': a.content_type,
            'url': _artifact_url(request, a.slug), 'content': a.content,
            'created_at': a.created_at.isoformat(),
        }, status=status.HTTP_200_OK)


# --- Audit ------------------------------------------------------------------

class AuditListView(ScopedView):
    required_scope = SCOPE_AUDIT

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 100))
        except (ValueError, TypeError):
            limit = 100
        limit = max(1, min(limit, 1000))
        logs = AuditLog.objects.all()[:limit]
        data = [{
            'id': log.id,
            'client': log.client_name,
            'action': log.action,
            'target': log.target,
            'status': log.status,
            'detail': log.detail,
            'ip': log.ip,
            'created_at': log.created_at.isoformat(),
        } for log in logs]
        return Response({'count': len(data), 'audit': data}, status=status.HTTP_200_OK)


# --- Utilitaire -------------------------------------------------------------

def _bad(exc):
    return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _coerce_obj(value, field):
    """
    Accepte un objet JSON OU une chaîne JSON (les GPT Actions envoient une
    chaîne pour les objets libres). Renvoie un dict.
    """
    if value in (None, ''):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            raise ValidationError(f"'{field}' doit être un objet JSON valide")
        if not isinstance(parsed, dict):
            raise ValidationError(f"'{field}' doit être un objet JSON")
        return parsed
    raise ValidationError(f"'{field}' doit être un objet JSON")
