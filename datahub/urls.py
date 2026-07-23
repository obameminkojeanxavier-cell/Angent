from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

from api.mcp import mcp_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    # Endpoint MCP HTTP (JSON-RPC). Enregistré avec et sans slash final car les
    # clients MCP ciblent souvent l'URL exacte /mcp.
    path('mcp', mcp_view, name='mcp'),
    path('mcp/', mcp_view, name='mcp-slash'),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]
