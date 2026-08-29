"""Deny-by-default serializers for client portal responses.

Each function explicitly lists allowed fields. A runtime safety net checks
that no field tagged in __internal_fields__ leaks through.
"""

from permissions import INTERNAL_ONLY_FIELDS


def _assert_no_internal_fields(data, model_name):
    """Runtime check — raises ValueError if any internal field is present."""
    if model_name not in INTERNAL_ONLY_FIELDS:
        return
    marker = INTERNAL_ONLY_FIELDS[model_name]
    if marker == '__all__':
        if data:
            raise ValueError(
                f"Model {model_name} is entirely internal — cannot serialize any fields. "
                f"Got keys: {list(data.keys())}"
            )
        return
    leaked = set(data.keys()) & marker
    if leaked:
        raise ValueError(
            f"Internal field(s) {leaked} from {model_name} leaked into portal response"
        )


def serialize_project_for_portal(project):
    """Safe project data for client portal."""
    data = {
        'id': project.id,
        'name': project.name,
        'status': project.status,
    }
    _assert_no_internal_fields(data, 'Project')
    return data


def serialize_invoice_for_portal(invoice):
    """Safe invoice data for client portal."""
    data = {
        'invoice_number': invoice.invoice_number,
        'status': invoice.status,
        'total_due': str(invoice.total_due),
        'balance_due': str(invoice.balance_due),
        'due_date': str(invoice.due_date) if invoice.due_date else None,
    }
    _assert_no_internal_fields(data, 'Invoice')
    return data


def serialize_change_order_for_portal(co):
    """Safe change order data for client portal — title + total only."""
    data = {
        'title': co.title,
        'status': co.status,
        'description': getattr(co, 'description', None),
        'price_to_client': str(co.price_to_client),
        'approved_at': str(co.approved_at) if co.approved_at else None,
    }
    _assert_no_internal_fields(data, 'ChangeOrder')
    return data


def serialize_phase_for_portal(phase):
    """Safe schedule phase data for client portal."""
    data = {
        'name': phase.client_label or phase.name,
        'color': phase.color,
        'status': getattr(phase, '_status', 'Coming up'),
        'done': getattr(phase, '_done', 0),
        'total': getattr(phase, '_total', 0),
    }
    return data


def serialize_selection_for_portal(selection):
    """Safe selection data for client portal."""
    data = {
        'status': selection.status,
        'note': selection.note,
    }
    _assert_no_internal_fields(data, 'ClientSelection')
    return data
