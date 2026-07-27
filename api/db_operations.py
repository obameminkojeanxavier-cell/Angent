from django.db import connection
from django.core.exceptions import ValidationError
from .validators import validate_identifier, validate_sql_type

# Plafond de lignes renvoyées par un SELECT, pour éviter de vider une grosse
# table en une requête (protection mémoire + exposition).
MAX_SELECT_LIMIT = 1000
DEFAULT_SELECT_LIMIT = 100


class DatabaseOperations:
    """Safe database operations with validated inputs."""
    
    @staticmethod
    def list_tables():
        """List all tables in the database."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            tables = [row[0] for row in cursor.fetchall()]
        return tables
    
    @staticmethod
    def create_table(table_name, columns):
        """
        Create a new table with specified columns.
        
        Args:
            table_name: Validated table name
            columns: Dict of {column_name: sql_type}
        """
        validate_identifier(table_name)
        
        column_defs = []
        for col_name, col_type in columns.items():
            validate_identifier(col_name)
            validate_sql_type(col_type)
            column_defs.append(f'"{col_name}" {col_type}')
        
        if not column_defs:
            raise ValueError("At least one column is required")
        
        with connection.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE "{table_name}" (
                    id SERIAL PRIMARY KEY,
                    {', '.join(column_defs)},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
    
    @staticmethod
    def add_column(table_name, column_name, column_type):
        """Add a column to an existing table."""
        validate_identifier(table_name)
        validate_identifier(column_name)
        validate_sql_type(column_type)
        
        with connection.cursor() as cursor:
            cursor.execute(f"""
                ALTER TABLE "{table_name}" 
                ADD COLUMN "{column_name}" {column_type};
            """)
    
    @staticmethod
    def insert(table_name, data):
        """
        Insert data into a table and return the complete record.

        Args:
            table_name: Validated table name
            data: Dict of {column_name: value}

        Returns:
            Dict with the complete inserted record including id and created_at
        """
        validate_identifier(table_name)

        if not data:
            raise ValueError("At least one column/value pair is required")

        columns = []
        values = []
        placeholders = []

        for col_name, value in data.items():
            validate_identifier(col_name)
            columns.append(f'"{col_name}"')
            values.append(value)
            placeholders.append('%s')

        with connection.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO "{table_name}" ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING *;
            """, values)
            columns = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            return dict(zip(columns, row))
    
    @staticmethod
    def select(table_name, filters=None, limit=None):
        """
        Select data from a table.
        
        Args:
            table_name: Validated table name
            filters: Dict of {column_name: value} for WHERE clause
            limit: Maximum number of rows to return
        """
        validate_identifier(table_name)
        
        query = f'SELECT * FROM "{table_name}"'
        params = []
        
        if filters:
            conditions = []
            for col_name, value in filters.items():
                validate_identifier(col_name)
                conditions.append(f'"{col_name}" = %s')
                params.append(value)
            
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)

        # Normalise et plafonne le limit. Un limit absent/invalide retombe sur
        # la valeur par défaut plutôt que de provoquer une erreur 500.
        if limit in (None, ''):
            limit = DEFAULT_SELECT_LIMIT
        else:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                raise ValidationError("'limit' must be an integer")
        limit = max(1, min(limit, MAX_SELECT_LIMIT))
        query += ' LIMIT %s'
        params.append(limit)

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(zip(columns, row)))
            
            return results
    
    @staticmethod
    def update(table_name, data, filters):
        """
        Update data in a table.
        
        Args:
            table_name: Validated table name
            data: Dict of {column_name: new_value}
            filters: Dict of {column_name: value} for WHERE clause
        """
        validate_identifier(table_name)
        
        if not data:
            raise ValueError("At least one column/value pair to update is required")
        
        if not filters:
            raise ValueError("At least one filter condition is required for safety")
        
        set_clauses = []
        params = []
        
        for col_name, value in data.items():
            validate_identifier(col_name)
            set_clauses.append(f'"{col_name}" = %s')
            params.append(value)
        
        where_clauses = []
        for col_name, value in filters.items():
            validate_identifier(col_name)
            where_clauses.append(f'"{col_name}" = %s')
            params.append(value)
        
        query = f"""
            UPDATE "{table_name}" 
            SET {', '.join(set_clauses)} 
            WHERE {' AND '.join(where_clauses)}
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    
    @staticmethod
    def delete(table_name, filters):
        """
        Delete data from a table.
        
        Args:
            table_name: Validated table name
            filters: Dict of {column_name: value} for WHERE clause
        """
        validate_identifier(table_name)
        
        if not filters:
            raise ValueError("At least one filter condition is required for safety")
        
        where_clauses = []
        params = []
        
        for col_name, value in filters.items():
            validate_identifier(col_name)
            where_clauses.append(f'"{col_name}" = %s')
            params.append(value)
        
        query = f"""
            DELETE FROM "{table_name}" 
            WHERE {' AND '.join(where_clauses)}
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    
    @staticmethod
    def get_table_schema(table_name):
        """Get the schema (columns) of a table."""
        validate_identifier(table_name)
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, [table_name])
            
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    'name': row[0],
                    'type': row[1],
                    'nullable': row[2] == 'YES'
                })

            return columns

    @staticmethod
    def count(table_name):
        """Nombre de lignes d'une table."""
        validate_identifier(table_name)
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            return cursor.fetchone()[0]

    @staticmethod
    def search(table_name, q, columns=None, limit=None):
        """
        Recherche insensible à la casse (ILIKE) de la sous-chaîne `q`.

        Si `columns` n'est pas fourni, recherche sur toutes les colonnes texte.
        Les identifiants sont validés ; la valeur recherchée est paramétrée.
        """
        validate_identifier(table_name)

        if not columns:
            schema = DatabaseOperations.get_table_schema(table_name)
            columns = [
                c['name'] for c in schema
                if 'char' in c['type'] or c['type'] in ('text',)
            ]

        conditions = []
        params = []
        for col_name in columns:
            validate_identifier(col_name)
            conditions.append(f'"{col_name}"::text ILIKE %s')
            params.append(f'%{q}%')

        query = f'SELECT * FROM "{table_name}"'
        if conditions:
            query += ' WHERE ' + ' OR '.join(conditions)

        if limit in (None, ''):
            limit = DEFAULT_SELECT_LIMIT
        else:
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                raise ValidationError("'limit' must be an integer")
        limit = max(1, min(limit, MAX_SELECT_LIMIT))
        query += ' LIMIT %s'
        params.append(limit)

        with connection.cursor() as cursor:
            cursor.execute(query, params)
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
