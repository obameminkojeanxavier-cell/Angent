from django.urls import path
from .views import (
    ListTablesView, CreateTableView, AddColumnView,
    InsertView, SelectView, UpdateView, DeleteView, TableSchemaView
)

# L'authentification et les permissions sont définies sur chaque vue
# (ReadView = lecture publique, WriteView = token requis).
urlpatterns = [
    path('tables/', ListTablesView.as_view(), name='list-tables'),
    path('tables/create/', CreateTableView.as_view(), name='create-table'),
    path('tables/add-column/', AddColumnView.as_view(), name='add-column'),
    path('tables/schema/', TableSchemaView.as_view(), name='table-schema'),
    path('data/insert/', InsertView.as_view(), name='insert'),
    path('data/select/', SelectView.as_view(), name='select'),
    path('data/update/', UpdateView.as_view(), name='update'),
    path('data/delete/', DeleteView.as_view(), name='delete'),
]
