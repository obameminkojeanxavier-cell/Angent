from django.urls import path
from .views import (
    ListTablesView, CreateTableView, AddColumnView, TableSchemaView,
    InsertView, SelectView, SearchView, UpdateView, DeleteView,
    SkillsListView, SkillRunView, TaskDetailView, TaskResultView,
    AuditListView,
)

# Auth et scopes définis sur chaque vue.
urlpatterns = [
    # Données — lecture
    path('tables/', ListTablesView.as_view(), name='list-tables'),
    path('tables/schema/', TableSchemaView.as_view(), name='table-schema'),
    path('data/select/', SelectView.as_view(), name='select'),
    path('data/search/', SearchView.as_view(), name='search'),

    # Données — écriture
    path('tables/create/', CreateTableView.as_view(), name='create-table'),
    path('tables/add-column/', AddColumnView.as_view(), name='add-column'),
    path('data/insert/', InsertView.as_view(), name='insert'),
    path('data/update/', UpdateView.as_view(), name='update'),
    path('data/delete/', DeleteView.as_view(), name='delete'),

    # Skills & tâches
    path('skills/', SkillsListView.as_view(), name='skills-list'),
    path('skills/<str:name>/run/', SkillRunView.as_view(), name='skill-run'),
    path('tasks/<uuid:task_id>/', TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<uuid:task_id>/result/', TaskResultView.as_view(), name='task-result'),

    # Audit
    path('audit/', AuditListView.as_view(), name='audit-list'),
]
