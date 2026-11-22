from flask import Blueprint, jsonify, current_app, request
from data.db import get_db
from mysql.connector import Error

bp = Blueprint('location', __name__, url_prefix='/api/location')

# Export as location_bp for import consistency
location_bp = bp


def _query_all(sql, params=()):
    """Execute a SELECT and return rows as list of dicts.
    Guarantees the cursor and connection are closed.
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    except Error as e:
        current_app.logger.error("Location API query failed: %s", e)
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _parent_exists(parent_table, parent_id_col, parent_id):
    """Return True if the parent record exists."""
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            f"SELECT 1 FROM {parent_table} WHERE {parent_id_col} = %s AND is_active = 1 LIMIT 1",
            (parent_id,),
        )
        return cur.fetchone() is not None
    except Error as e:
        current_app.logger.error("Location API parent check failed: %s", e)
        raise
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@bp.route('/states')
def get_states():
    try:
        rows = _query_all(
            'SELECT id, name FROM states WHERE is_active = 1 ORDER BY name'
        )
        return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])
    except Error:
        return jsonify({'error': 'database_error', 'message': 'Unable to load states.'}), 500


@bp.route('/districts/<int:state_id>')
def get_districts(state_id):
    if state_id <= 0:
        return jsonify({'error': 'validation_error', 'message': 'Invalid state id.'}), 400
    try:
        if not _parent_exists('states', 'id', state_id):
            return jsonify({'error': 'not_found', 'message': 'State not found.'}), 404
        rows = _query_all(
            'SELECT id, name FROM districts WHERE state_id = %s AND is_active = 1 ORDER BY name',
            (state_id,),
        )
        return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])
    except Error:
        return jsonify({'error': 'database_error', 'message': 'Unable to load districts.'}), 500


@bp.route('/tehsils/<int:district_id>')
def get_tehsils(district_id):
    if district_id <= 0:
        return jsonify({'error': 'validation_error', 'message': 'Invalid district id.'}), 400
    try:
        if not _parent_exists('districts', 'id', district_id):
            return jsonify({'error': 'not_found', 'message': 'District not found.'}), 404
        rows = _query_all(
            'SELECT id, name FROM tehsils WHERE district_id = %s AND is_active = 1 ORDER BY name',
            (district_id,),
        )
        return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])
    except Error:
        return jsonify({'error': 'database_error', 'message': 'Unable to load tehsils.'}), 500


@bp.route('/villages/<int:tehsil_id>')
def get_villages(tehsil_id):
    if tehsil_id <= 0:
        return jsonify({'error': 'validation_error', 'message': 'Invalid tehsil id.'}), 400
    try:
        if not _parent_exists('tehsils', 'id', tehsil_id):
            return jsonify({'error': 'not_found', 'message': 'Tehsil not found.'}), 404
        rows = _query_all(
            'SELECT id, name FROM villages WHERE tehsil_id = %s AND is_active = 1 ORDER BY name',
            (tehsil_id,),
        )
        return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])
    except Error:
        return jsonify({'error': 'database_error', 'message': 'Unable to load villages.'}), 500


@bp.route('/location-names', methods=['POST'])
def get_location_names():
    """Resolve location IDs to names. Body: JSON with optional state_id, district_id, tehsil_id, village_id."""
    conn = None
    cur = None
    try:
        payload = request.get_json(silent=True) or {}
        result = {}
        conn = get_db()
        cur = conn.cursor()
        for field, table in (
            ('state', 'states'),
            ('district', 'districts'),
            ('tehsil', 'tehsils'),
            ('village', 'villages'),
        ):
            raw = payload.get(f'{field}_id')
            if raw in (None, ''):
                result[f'{field}_id'] = None
                result[f'{field}_name'] = None
                continue
            try:
                lid = int(raw)
            except (TypeError, ValueError):
                return jsonify({'error': 'validation_error', 'message': f'Invalid {field} id.'}), 400
            cur.execute(f'SELECT name FROM {table} WHERE id = %s AND is_active = 1', (lid,))
            row = cur.fetchone()
            if row is None:
                return jsonify({'error': 'not_found', 'message': f'{field.title()} not found.'}), 404
            result[f'{field}_id'] = lid
            result[f'{field}_name'] = row[0]
        return jsonify(result)
    except Error:
        return jsonify({'error': 'database_error', 'message': 'Unable to resolve location names.'}), 500
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
