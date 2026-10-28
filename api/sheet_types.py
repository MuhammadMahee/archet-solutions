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
