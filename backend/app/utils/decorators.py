from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt

def role_required(*roles):
    """
    Decorator to restrict route access to specified user roles.
    Expects @jwt_required() to be applied to the route as well.
    
    Usage:
        @app.route("/api/admin/users")
        @jwt_required()
        @role_required("admin")
        def admin_only_route():
            ...
    """
    allowed_roles = {str(r).lower() for r in roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get("role")
            
            if not user_role or str(user_role).lower() not in allowed_roles:
                return jsonify({"error": "Forbidden: Insufficient privileges for this role"}), 403
                
            return fn(*args, **kwargs)
        return wrapper
    return decorator
