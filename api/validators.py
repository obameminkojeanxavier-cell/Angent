import re
from django.core.exceptions import ValidationError


def validate_identifier(name):
    """
    Validate table and column names to prevent SQL injection.
    Only allows alphanumeric characters and underscores.
    """
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValidationError(
            f"Invalid identifier '{name}'. Only alphanumeric characters and underscores are allowed."
        )
    if len(name) > 63:
        raise ValidationError(
            f"Identifier '{name}' is too long. Maximum length is 63 characters."
        )
    return name


def validate_sql_type(sql_type):
    """
    Validate SQL column types to prevent injection.
    """
    allowed_types = [
        'integer', 'bigint', 'smallint',
        'varchar', 'text', 'char',
        'boolean',
        'decimal', 'numeric', 'real', 'double precision',
        'date', 'time', 'timestamp',
        'json', 'jsonb',
        'uuid'
    ]
    
    sql_type_lower = sql_type.lower().strip()
    
    # Check for basic types
    if sql_type_lower in allowed_types:
        return sql_type_lower
    
    # Check for varchar with length
    if sql_type_lower.startswith('varchar(') and sql_type_lower.endswith(')'):
        try:
            length = int(sql_type_lower[:-1].split('(')[1])
            if 1 <= length <= 65535:
                return sql_type_lower
        except (ValueError, IndexError):
            pass
    
    raise ValidationError(
        f"Invalid SQL type '{sql_type}'. Allowed types: {', '.join(allowed_types)}"
    )
