from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

from api.mcp import mcp_view
from api.docs import skill_doc, api_doc
from api.console import console_run, console_skills

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # Documents téléchargeables (contrat d'intégration pour les IA/skills)
    path('api.md', api_doc, name='api-doc'),
    path('skill.md', skill_doc, name='skill-doc'),
    # Console d'exécution (interface GOD HAND)
    path('console/skills', console_skills, name='console-skills'),
    path('console/run', console_run, name='console-run'),
    # Endpoint MCP HTTP (JSON-RPC). Enregistré avec et sans slash final car les
    # clients MCP ciblent souvent l'URL exacte /mcp.
    path('mcp', mcp_view, name='mcp'),
    path('mcp/', mcp_view, name='mcp-slash'),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]
