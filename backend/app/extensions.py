"""
Shared Flask extension instances.

These are instantiated WITHOUT an app here, then bound to the actual app
inside app/__init__.py's create_app() via each extension's .init_app(app).
This pattern avoids circular imports: db_models/, routes/, services/ etc.
can all `from app.extensions import db` without needing the app instance
to exist yet.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
socketio = SocketIO()

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data.get("sub")
    if not identity or not str(identity).isdigit():
        return None
    from app.db_models.user import User
    user = db.session.get(User, int(identity))
    if user and not user.is_active:
        return None  # Rejects deactivated user tokens immediately
    return user