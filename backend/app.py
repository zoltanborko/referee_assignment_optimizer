import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session

from auth import roles_required
from services.auth_service import (
    authenticate,
    change_password,
    create_user,
    list_users,
    reset_user_password,
    set_user_active,
)

from services.excel_import import import_matches_from_excel
from services.ref_pool_service import load_ref_pool, load_ref_pool_for_date, set_ref_pool
from services.referee_service import (
    add_referee,
    delete_referee,
    load_referees,
    update_own_referee,
    update_referee,
)
from services.match_pool_service import (
    create_match_pool,
    delete_upload,
    finalize_upload,
    get_upload,
    list_uploads,
    load_upload_matches,
    list_notifications,
    load_matches as load_matchpool_matches,
    load_referee_matches,
    get_upload_referee_exclusions,
    set_upload_referee_exclusions,
    mark_notification_read,
)


app = Flask(__name__)
app.json.sort_keys = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE", "").lower()
    in {"1", "true", "yes"},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.before_request
def require_csrf_token():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    expected = session.get("csrf_token")
    received = request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected, received):
        return jsonify({"error": "Hiányzó vagy érvénytelen CSRF-token."}), 400
    return None


# ---------------------------------------------------------
# Főoldal
# ---------------------------------------------------------

@app.route("/auth/csrf", methods=["GET"])
def auth_csrf():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return jsonify({"csrf_token": token})


@app.route("/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A bejelentkezési adatok hibásak."}), 400
    user = authenticate(payload.get("username"), payload.get("password"))
    if user is None:
        return jsonify({"error": "Hibás felhasználónév vagy jelszó."}), 401
    session.clear()
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({
        "user": {
            "username": user["username"],
            "role": user["role"],
            "must_change_password": user["must_change_password"],
        },
        "csrf_token": session["csrf_token"],
    })


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"message": "Sikeres kijelentkezés."})


@app.route("/auth/me", methods=["GET"])
@roles_required("admin", "sender", "referee", allow_password_change=True)
def auth_me():
    return jsonify({
        "user": {
            "username": g.user["username"],
            "role": g.user["role"],
            "must_change_password": g.user["must_change_password"],
        }
    })


@app.route("/auth/change-password", methods=["POST"])
@roles_required("admin", "sender", "referee", allow_password_change=True)
def auth_change_password():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        user = change_password(
            g.user["user_id"],
            payload.get("current_password"),
            payload.get("new_password"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({
        "message": "A jelszó megváltozott.",
        "user": {"username": user["username"], "role": user["role"]},
    })


@app.route("/users", methods=["GET"])
@roles_required("admin")
def get_users():
    return jsonify({"users": list_users()})


@app.route("/users", methods=["POST"])
@roles_required("admin")
def create_account():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        user = create_user(payload.get("username"), payload.get("role"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({
        "user": {"username": user["username"], "role": user["role"]},
        "initial_password": user["username"],
        "must_change_password": True,
    }), 201


@app.route("/users/<int:user_id>/active", methods=["PUT"])
@roles_required("admin")
def update_user_active(user_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        user = set_user_active(user_id, payload.get("active"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if user is None:
        return jsonify({"error": "A nem-játékvezető fiók nem található."}), 404
    return jsonify({"user": user})


@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@roles_required("admin")
def reset_account_password(user_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        user = reset_user_password(user_id, payload.get("temporary_password"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if user is None:
        return jsonify({"error": "Az aktív fiók nem található."}), 404
    return jsonify({
        "message": "Az ideiglenes jelszó beállítva; a következő belépéskor cserélni kell.",
        "username": user["username"],
    })

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/assets/<path:filename>")
def frontend_assets(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ---------------------------------------------------------
# Játékvezetők
# ---------------------------------------------------------

@app.route("/referees", methods=["GET"])
@roles_required("admin", "sender")
def get_referees():
    return jsonify({"referees": load_referees()})


@app.route("/referees", methods=["POST"])
@roles_required("admin")
def create_referee():
    try:
        referee = add_referee(request.get_json(silent=True))
        return jsonify({"referee": referee}), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/referees/<referee_id>", methods=["PUT"])
@roles_required("admin")
def edit_referee(referee_id):
    try:
        referee = update_referee(referee_id, request.get_json(silent=True))
        if referee is None:
            return jsonify({"error": "A játékvezető nem található."}), 404
        return jsonify({"referee": referee})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.route("/referees/<referee_id>", methods=["DELETE"])
@roles_required("admin")
def remove_referee(referee_id):
    if not delete_referee(referee_id):
        return jsonify({"error": "A játékvezető nem található."}), 404
    return jsonify({"message": "A játékvezető törlése sikerült."})


@app.route("/ref-pool", methods=["GET"])
@roles_required("admin", "sender")
def get_ref_pool():
    return jsonify({"refPool": load_ref_pool()})


@app.route("/ref-pool", methods=["POST"])
@roles_required("admin", "sender")
def update_ref_pool():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A kérés adatai hibásak."}), 400
    try:
        ref_pool = set_ref_pool(payload.get("referee_ids"))
        return jsonify({
            "message": f"{len(ref_pool)} elérhető játékvezető került a refPool-ba.",
            "refPool": ref_pool,
        })
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


# ---------------------------------------------------------
# Mérkőzések feltöltése
# ---------------------------------------------------------

@app.route("/me/referee", methods=["GET"])
@roles_required("referee")
def get_my_referee_profile():
    referee = next(
        (item for item in load_referees()
         if str(item.get("id")) == str(g.user["referee_id"])),
        None,
    )
    if referee is None:
        return jsonify({"error": "A játékvezetői profil nem található."}), 404
    return jsonify({"referee": referee})


@app.route("/me/referee", methods=["PUT"])
@roles_required("referee")
def edit_my_referee_profile():
    try:
        referee = update_own_referee(
            g.user["referee_id"], request.get_json(silent=True)
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if referee is None:
        return jsonify({"error": "A játékvezetői profil nem található."}), 404
    return jsonify({"referee": referee})


@app.route("/me/matches", methods=["GET"])
@roles_required("referee")
def get_my_matches():
    return jsonify({"matches": load_referee_matches(g.user["referee_id"])})


@app.route("/notifications", methods=["GET"])
@roles_required("admin", "sender")
def get_notifications():
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    return jsonify({"notifications": list_notifications(owner_id)})


@app.route("/notifications/<int:notification_id>/read", methods=["POST"])
@roles_required("admin", "sender")
def read_notification(notification_id):
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    if not mark_notification_read(notification_id, owner_id):
        return jsonify({"error": "Az értesítés nem található."}), 404
    return jsonify({"message": "Az értesítés olvasottnak jelölve."})

@app.route("/matches", methods=["POST"])
@roles_required("admin", "sender")
def upload_matches():

    if "file" not in request.files:
        return jsonify({
            "error": "Nem érkezett fájl."
        }), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({
            "error": "Nincs kiválasztott fájl."
        }), 400

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({
            "error": "Csak Excel-fájl tölthető fel."
        }), 400

    try:

        matches, warnings = import_matches_from_excel(file)

        upload_id = create_match_pool(
            matches,
            created_by=g.user["user_id"],
            source_filename=file.filename,
        )

        return jsonify({
            "message": "A mérkőzések sikeresen feltöltve.",
            "count": len(matches),
            "warnings": warnings,
            "matches": matches,
            "upload_id": upload_id,
        }), 201
        
        

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400

    except Exception as error:

        return jsonify({
            "error": (
                "Hiba történt a fájl feldolgozása során: "
                f"{str(error)}"
            )
        }), 500


# ---------------------------------------------------------
# Mérkőzések lekérése
# ---------------------------------------------------------

@app.route("/uploads", methods=["GET"])
@roles_required("admin", "sender")
def get_uploads():
    uploads = list_uploads()
    for upload in uploads:
        upload["is_owner"] = (
            g.user["role"] == "admin"
            or upload.get("created_by") == g.user["user_id"]
        )
    return jsonify({"uploads": uploads})


@app.route("/uploads/<int:upload_id>", methods=["GET"])
@roles_required("admin", "sender")
def get_upload_detail(upload_id):
    upload = get_upload(upload_id)
    if upload is None:
        return jsonify({"error": "A feltöltés nem található."}), 404
    upload["matches"] = load_upload_matches(upload_id)
    return jsonify({"upload": upload})


@app.route("/uploads/<int:upload_id>/referee-exclusions", methods=["GET"])
@roles_required("admin", "sender")
def get_upload_exclusions(upload_id):
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    upload = get_upload(upload_id, owner_id)
    if upload is None:
        return jsonify({"error": "A feltöltés nem található."}), 404
    exclusions = get_upload_referee_exclusions(upload_id)
    return jsonify({
        "dates": [
            {
                "date": match_date,
                "referees": load_ref_pool_for_date(match_date),
                "excluded_ids": exclusions.get(match_date, []),
            }
            for match_date in upload["dates"]
        ]
    })


@app.route("/uploads/<int:upload_id>/referee-exclusions", methods=["PUT"])
@roles_required("admin", "sender")
def update_upload_exclusions(upload_id):
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    upload = get_upload(upload_id, owner_id)
    if upload is None:
        return jsonify({"error": "A feltöltés nem található."}), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A letiltási adatok hibásak."}), 400
    match_date = payload.get("match_date")
    referee_ids = payload.get("excluded_referee_ids")
    if match_date not in upload["dates"]:
        return jsonify({"error": "Ez a dátum nem szerepel a feltöltésben."}), 400
    if not isinstance(referee_ids, list) or any(
        isinstance(referee_id, bool) or not isinstance(referee_id, (str, int))
        for referee_id in referee_ids
    ):
        return jsonify({"error": "A letiltott játékvezető-azonosítók listája hibás."}), 400
    referee_ids = list(dict.fromkeys(str(referee_id).strip() for referee_id in referee_ids))
    if any(not referee_id for referee_id in referee_ids):
        return jsonify({"error": "A játékvezető-azonosító nem lehet üres."}), 400
    eligible_ids = {
        str(referee.get("id")) for referee in load_ref_pool_for_date(match_date)
    }
    if not set(referee_ids).issubset(eligible_ids):
        return jsonify({"error": "Csak az adott napon elérhető refpool-játékvezetők tilthatók le."}), 400
    set_upload_referee_exclusions(upload_id, match_date, referee_ids)
    return jsonify({"message": "A letiltások elmentve.", "excluded_referee_ids": referee_ids})


@app.route("/uploads/<int:upload_id>/assign", methods=["POST"])
@roles_required("admin", "sender")
def run_upload_assignment(upload_id):
    from services.assigner_service import assign_upload

    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    result = assign_upload(upload_id, owner_id)
    if result is None:
        return jsonify({"error": "A feltöltés nem található."}), 404
    return jsonify({"assignment": result})


@app.route("/uploads/<int:upload_id>/finalize", methods=["POST"])
@roles_required("admin", "sender")
def finalize_upload_assignment(upload_id):
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    upload, error = finalize_upload(upload_id, owner_id)
    if error == "not_found":
        return jsonify({"error": "A feltöltés nem található."}), 404
    if error == "no_draft":
        return jsonify({"error": "Nincs véglegesíthető kiosztási piszkozat."}), 409
    if error == "no_assignments":
        return jsonify({"error": "Egyetlen mérkőzéshez sem sikerült stábot rendelni."}), 409
    return jsonify({
        "message": "A küldés véglegesítve; a játékvezetők látják a saját mérkőzéseiket.",
        "upload": upload,
    })


@app.route("/uploads/<int:upload_id>", methods=["DELETE"])
@roles_required("admin", "sender")
def remove_upload(upload_id):
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    if not delete_upload(upload_id, owner_id):
        return jsonify({"error": "A feltöltés nem található."}), 404
    return jsonify({"message": "A feltöltés és a hozzá tartozó kiosztás törölve."})

@app.route("/matches", methods=["GET"])
@roles_required("admin", "sender")
def get_matches():
    owner_id = None if g.user["role"] == "admin" else g.user["user_id"]
    matches = load_matchpool_matches(request.args.get("date"), owner_id)

    return jsonify({
        "matches": matches
    })


# ---------------------------------------------------------
# Szerver indítása
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
