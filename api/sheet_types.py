"""Request-scoped spreadsheet definitions; shared sources, isolated editable data."""
from flask import has_request_context, request

COMPLIANCE_COLUMNS = [('date','Date'),('dealer_name','Dealer'),('market','Market'),('store','Store'),('employee','Employee'),
    ('store_cleaning','Store Cleaning'),('name_tag','Name Tag'),('shirt','Shirt'),('shoes','Shoes'),
    ('safe_closed','Safe Closed'),('demos_removed','Demos Removed'),('alarm_activated','Alarm Activated')]
CHECK_FIELDS = {key for key, _ in COMPLIANCE_COLUMNS[5:]}
CHECK_COLORS = {'No': ('9C0006','FFC7CE'), 'Yes': ('006100','C6EFCE'), '#N/A': ('9C5700','FFEB9C')}
CAMERA_OFFLINE = 'Camera Offline'


def compliance():
    return has_request_context() and request.path.startswith('/api/internal/compliance')


def sheet_table(suffix):
    if suffix not in {'reviews','employee_reviews','manual_employees','versions','sheet_settings','live_revision','presence'}:
        raise ValueError('Unknown spreadsheet table')
    return 'public.' + ('compliance_' if compliance() else 'store_hours_') + suffix


def report_columns():
    from api.store_hours import COLUMNS
    return COMPLIANCE_COLUMNS if compliance() else COLUMNS


def cell_colors(key, value):
    if compliance() and key in CHECK_FIELDS:
        return CHECK_COLORS.get(value)
    if value in ('Late', 'Early') or (key == 'chargeback' and value is not None and value < 0):
        return CHECK_COLORS['No']
    if value in ('Open', 'On Time'):
        return CHECK_COLORS['Yes']
    if value in ('Pending camera review', 'Schedule required', CAMERA_OFFLINE) or (key == 'chargeback' and value is None):
        return CHECK_COLORS['#N/A']
    if key in ('rt_clockin', 'rt_clockout') and not value:
        return CHECK_COLORS['No']
    return None
