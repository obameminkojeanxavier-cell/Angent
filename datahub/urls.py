from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

from api.mcp import mcp_view
from api.docs import skill_doc, api_doc
from api.console import console_run, console_skills
from api.openapi import openapi_schema
from api.artifacts import render_artifact
from api import manage as mng

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # Documents téléchargeables (contrat d'intégration pour les IA/skills)
    path('api.md', api_doc, name='api-doc'),
    path('skill.md', skill_doc, name='skill-doc'),
    # Schéma OpenAPI pour les "Actions" d'un GPT personnalisé (ChatGPT)
    path('openapi.json', openapi_schema, name='openapi'),
    # Rendu public des artefacts (fichiers produits par les agents)
    path('a/<str:slug>', render_artifact, name='artifact-render'),
    path('a/<str:slug>/', render_artifact),

    # Catalogue public des skills (page d'accueil dynamique)
    path('public/skills', mng.public_skills, name='public-skills'),

    # Tableau de bord d'administration (GOD HAND) — réservé au staff connecté
    path('manage/', mng.dashboard, name='dashboard'),
    path('manage/login/', mng.login_view, name='manage-login'),
    path('manage/logout/', mng.logout_view, name='manage-logout'),
    path('manage/api/overview', mng.overview),
    path('manage/api/agents/create', mng.agent_create),
    path('manage/api/agents/<int:agent_id>/update', mng.agent_update),
    path('manage/api/agents/<int:agent_id>/delete', mng.agent_delete),
    path('manage/api/skills', mng.skills_list),
    path('manage/api/skills/create', mng.skill_create),
    path('manage/api/skills/import', mng.skill_import),
    path('manage/api/skills/<str:name>/detail', mng.skill_detail),
    path('manage/api/skills/<str:name>/toggle', mng.skill_toggle),
    path('manage/api/skills/<str:name>/delete', mng.skill_delete),
    # Console d'exécution (interface GOD HAND)
    path('console/skills', console_skills, name='console-skills'),
    path('console/run', console_run, name='console-run'),
    # Endpoint MCP HTTP (JSON-RPC). Enregistré avec et sans slash final car les
    # clients MCP ciblent souvent l'URL exacte /mcp.
    path('mcp', mcp_view, name='mcp'),
    path('mcp/', mcp_view, name='mcp-slash'),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]
