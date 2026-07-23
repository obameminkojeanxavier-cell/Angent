from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.core.exceptions import ValidationError
from .authentication import TokenAuthentication
from .db_operations import DatabaseOperations


class ReadView(APIView):
    """Base pour les endpoints de LECTURE : consultation publique (sans token).

    Un token reste accepté s'il est fourni, mais il n'est pas requis — c'est ce
    qui permet à la page web de consultation de fonctionner sans secret.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [AllowAny]


class WriteView(APIView):
    """Base pour les endpoints d'ÉCRITURE : token API obligatoire."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


class ListTablesView(ReadView):
    def get(self, request):
        try:
            tables = DatabaseOperations.list_tables()
            return Response({'tables': tables}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateTableView(WriteView):
    def post(self, request):
        try:
            table_name = request.data.get('table_name')
            columns = request.data.get('columns', {})
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not columns:
                return Response(
                    {'error': 'columns dict is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            DatabaseOperations.create_table(table_name, columns)
            return Response(
                {'message': f'Table {table_name} created successfully'}, 
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddColumnView(WriteView):
    def post(self, request):
        try:
            table_name = request.data.get('table_name')
            column_name = request.data.get('column_name')
            column_type = request.data.get('column_type')
            
            if not all([table_name, column_name, column_type]):
                return Response(
                    {'error': 'table_name, column_name, and column_type are required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            DatabaseOperations.add_column(table_name, column_name, column_type)
            return Response(
                {'message': f'Column {column_name} added to {table_name}'}, 
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InsertView(WriteView):
    def post(self, request):
        try:
            table_name = request.data.get('table_name')
            data = request.data.get('data', {})
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not data:
                return Response(
                    {'error': 'data dict is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            row_id = DatabaseOperations.insert(table_name, data)
            return Response(
                {'message': 'Data inserted successfully', 'id': row_id}, 
                status=status.HTTP_201_CREATED
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SelectView(ReadView):
    def get(self, request):
        try:
            table_name = request.query_params.get('table_name')
            filters = request.query_params.dict()
            filters.pop('table_name', None)
            limit = request.query_params.get('limit')
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse filters from query params
            parsed_filters = {}
            for key, value in filters.items():
                if key != 'limit':
                    parsed_filters[key] = value
            
            results = DatabaseOperations.select(table_name, parsed_filters, limit)
            return Response({'data': results}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateView(WriteView):
    def put(self, request):
        try:
            table_name = request.data.get('table_name')
            data = request.data.get('data', {})
            filters = request.data.get('filters', {})
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not data:
                return Response(
                    {'error': 'data dict is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not filters:
                return Response(
                    {'error': 'filters dict is required for safety'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            row_count = DatabaseOperations.update(table_name, data, filters)
            return Response(
                {'message': f'{row_count} row(s) updated'}, 
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteView(WriteView):
    def delete(self, request):
        try:
            table_name = request.data.get('table_name')
            filters = request.data.get('filters', {})
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not filters:
                return Response(
                    {'error': 'filters dict is required for safety'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            row_count = DatabaseOperations.delete(table_name, filters)
            return Response(
                {'message': f'{row_count} row(s) deleted'}, 
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TableSchemaView(ReadView):
    def get(self, request):
        try:
            table_name = request.query_params.get('table_name')
            
            if not table_name:
                return Response(
                    {'error': 'table_name is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            schema = DatabaseOperations.get_table_schema(table_name)
            return Response({'schema': schema}, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
