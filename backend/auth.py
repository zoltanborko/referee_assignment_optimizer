"""Flask request authentication and role-based access decorators."""

from functools import wraps

from flask import g, jsonify, session

from services.auth_service import get_user


def _current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = get_user(user_id)
    if user is None or not user["active"]:
        session.clear()
        return None
    return user


def login_required(allow_password_change=False):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user is None:
                return jsonify({"error": "Bejelentkezés szükséges."}), 401
            if (
                user["must_change_password"]
                and not allow_password_change
            ):
                return jsonify({
                    "error": "Az első használat előtt meg kell változtatni a jelszót.",
                    "password_change_required": True,
                }), 403
            g.user = user
            return view(*args, **kwargs)
        return wrapped
    return decorator


def roles_required(*roles, allow_password_change=False):
    def decorator(view):
        @wraps(view)
        @login_required(allow_password_change=allow_password_change)
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return jsonify({"error": "Nincs jogosultság ehhez a művelethez."}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator
