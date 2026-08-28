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
        'start_date': str(project.start_date) if project.start_date else None,
        'end_date': str(project.end_date) if project.end_date else None,
    }
    _assert_no_internal_fields(data, 'Project')
    return data


def serialize_invoice_for_portal(invoice):
    """Safe invoice data for client portal."""
    data = {
        'id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'status': invoice.status,
        'subtotal': str(invoice.subtotal),
        'total_due': str(invoice.total_due),
        'amount_paid': str(invoice.amount_paid),
        'balance_due': str(invoice.balance_due),
        'issued_date': str(invoice.issued_date) if invoice.issued_date else None,
        'due_date': str(invoice.due_date) if invoice.due_date else None,
        'notes': invoice.notes,
    }
    _assert_no_internal_fields(data, 'Invoice')
    return data


def serialize_change_order_for_portal(co):
    """Safe change order data for client portal."""
    data = {
        'id': co.id,
        'co_number': co.co_number,
        'title': co.title,
        'status': co.status,
        'description': getattr(co, 'description', None),
    }
    _assert_no_internal_fields(data, 'ChangeOrder')
    return data


def serialize_schedule_task_for_portal(task):
    """Safe schedule task data for client portal."""
    data = {
        'id': task.id,
        'name': task.name,
        'status': task.status,
        'start_date': str(task.start_date) if task.start_date else None,
        'end_date': str(task.end_date) if task.end_date else None,
    }
    _assert_no_internal_fields(data, 'ScheduleTask')
    return data


def serialize_selection_for_portal(selection):
    """Safe selection data for client portal."""
    data = {
        'id': selection.id,
        'status': selection.status,
    }
    _assert_no_internal_fields(data, 'ClientSelection')
    return data
