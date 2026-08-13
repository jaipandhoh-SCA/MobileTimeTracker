"""Tests for cost math, estimate calculations, invoice recalculation,
and CostEntry upsert idempotency.

Verifies:
1. Project.total_budget / total_actual / total_committed / cost_to_complete
2. EstimateLineItem extended_cost with waste
3. Estimate subtotal / overhead / markup / contingency / total
4. Invoice.recalculate correctness
5. CostEntry.upsert_for_time_entry idempotency
6. Budget variance math (budget_used_pct)
7. ChangeOrder.item_total aggregation
"""

import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

os.environ.setdefault('SESSION_SECRET', 'test-secret-key-for-testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('ALLOW_DEV_LOGIN', 'false')

from app import app, db
from models import (
    User, Client, Project, CostCode, Budget, CostEntry,
    Estimate, EstimateLineItem,
    Invoice, InvoiceLineItem, Payment,
    Contract, Proposal, DrawScheduleItem,
    ChangeOrder, ChangeOrderItem,
    TimeEntry,
)


class CostMathBase(unittest.TestCase):
    """Shared setup: creates a project with cost codes and a staff user."""

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost'
        self.app_ctx = app.app_context()
        self.app_ctx.push()
        db.create_all()

        self.user = User(id='test-user-001', email='test@co.com',
                         first_name='Test', last_name='User', role='supervisor')
        db.session.add(self.user)

        self.client_obj = Client(name='Test Client', address='100 Main',
                                 status='Active', contact_name='TC')
        db.session.add(self.client_obj)
        db.session.flush()

        self.project = Project(
            client_id=self.client_obj.id, name='Test ADU',
            contract_value=Decimal('250000'), status='In Progress',
            is_default=True,
        )
        db.session.add(self.project)
        db.session.flush()

        # Cost codes
        self.cc_site = CostCode(code='01', name='Site Work', sort_order=1)
        self.cc_found = CostCode(code='02', name='Foundation', sort_order=2)
        self.cc_frame = CostCode(code='03', name='Framing', sort_order=3)
        db.session.add_all([self.cc_site, self.cc_found, self.cc_frame])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_ctx.pop()


class TestProjectBudgetActualCommitted(CostMathBase):
    """Project.total_budget, total_actual, total_committed, cost_to_complete."""

    def test_empty_project_returns_zeros(self):
        self.assertEqual(self.project.total_budget, Decimal('0'))
        self.assertEqual(self.project.total_actual, Decimal('0'))
        self.assertEqual(self.project.total_committed, Decimal('0'))
        self.assertEqual(self.project.cost_to_complete, Decimal('0'))

    def test_budget_sums_correctly(self):
        db.session.add_all([
            Budget(project_id=self.project.id, cost_code_id=self.cc_site.id,
                   cost_type='Material', amount=Decimal('15000')),
            Budget(project_id=self.project.id, cost_code_id=self.cc_found.id,
                   cost_type='Labor', amount=Decimal('25000')),
        ])
        db.session.commit()
        self.assertEqual(self.project.total_budget, Decimal('40000'))

    def test_actual_excludes_committed(self):
        db.session.add_all([
            CostEntry(project_id=self.project.id, cost_code_id=self.cc_site.id,
                      cost_type='Material', source='manual',
                      amount=Decimal('5000'), entry_date=date.today(),
                      committed=False, created_by_user_id=self.user.id),
            CostEntry(project_id=self.project.id, cost_code_id=self.cc_site.id,
                      cost_type='Material', source='po',
                      amount=Decimal('8000'), entry_date=date.today(),
                      committed=True, created_by_user_id=self.user.id),
        ])
        db.session.commit()
        self.assertEqual(self.project.total_actual, Decimal('5000'))
        self.assertEqual(self.project.total_committed, Decimal('8000'))

    def test_cost_to_complete(self):
        """CTC = budget - actual - committed."""
        db.session.add(Budget(
            project_id=self.project.id, cost_code_id=self.cc_site.id,
            cost_type='Material', amount=Decimal('50000'),
        ))
        db.session.add(CostEntry(
            project_id=self.project.id, cost_code_id=self.cc_site.id,
            cost_type='Material', source='manual',
            amount=Decimal('10000'), entry_date=date.today(),
            committed=False, created_by_user_id=self.user.id,
        ))
        db.session.add(CostEntry(
            project_id=self.project.id, cost_code_id=self.cc_site.id,
            cost_type='Material', source='po',
            amount=Decimal('5000'), entry_date=date.today(),
            committed=True, created_by_user_id=self.user.id,
        ))
        db.session.commit()
        self.assertEqual(self.project.cost_to_complete, Decimal('35000'))

    def test_budget_used_pct(self):
        db.session.add(Budget(
            project_id=self.project.id, cost_code_id=self.cc_site.id,
            cost_type='Material', amount=Decimal('100000'),
        ))
        db.session.add(CostEntry(
            project_id=self.project.id, cost_code_id=self.cc_site.id,
            cost_type='Material', source='manual',
            amount=Decimal('75000'), entry_date=date.today(),
            committed=False, created_by_user_id=self.user.id,
        ))
        db.session.commit()
        self.assertEqual(self.project.budget_used_pct, Decimal('75.0'))

    def test_budget_used_pct_zero_budget(self):
        """No budget => 0% used, not division by zero."""
        self.assertEqual(self.project.budget_used_pct, Decimal('0'))


class TestCostEntryUpsert(CostMathBase):
    """CostEntry.upsert_for_time_entry must be idempotent."""

    def test_upsert_creates_new(self):
        te = TimeEntry(
            user_id=self.user.id, client_id=self.client_obj.id,
            date=date.today(), start_time=datetime.now(timezone.utc),
            duration_hours=Decimal('4.00'),
            work_description='Foundation work',
        )
        db.session.add(te)
        db.session.flush()

        ce = CostEntry.upsert_for_time_entry(
            te.id,
            project_id=self.project.id, cost_code_id=self.cc_found.id,
            cost_type='Labor', source='time',
            amount=Decimal('200.00'), entry_date=date.today(),
            created_by_user_id=self.user.id,
        )
        db.session.commit()
        self.assertIsNotNone(ce.id)
        self.assertEqual(ce.amount, Decimal('200.00'))

    def test_upsert_updates_existing(self):
        """Second call with same time_entry_id updates, doesn't duplicate."""
        te = TimeEntry(
            user_id=self.user.id, client_id=self.client_obj.id,
            date=date.today(), start_time=datetime.now(timezone.utc),
            duration_hours=Decimal('4.00'),
            work_description='Foundation work',
        )
        db.session.add(te)
        db.session.flush()

        ce1 = CostEntry.upsert_for_time_entry(
            te.id,
            project_id=self.project.id, cost_code_id=self.cc_found.id,
            cost_type='Labor', source='time',
            amount=Decimal('200.00'), entry_date=date.today(),
            created_by_user_id=self.user.id,
        )
        db.session.commit()
        first_id = ce1.id

        ce2 = CostEntry.upsert_for_time_entry(
            te.id,
            amount=Decimal('250.00'),
        )
        db.session.commit()

        self.assertEqual(ce2.id, first_id, 'Should update, not create new')
        self.assertEqual(ce2.amount, Decimal('250.00'))

        count = CostEntry.query.filter_by(time_entry_id=te.id).count()
        self.assertEqual(count, 1, 'Should have exactly one entry')


class TestEstimateMath(CostMathBase):
    """Estimate subtotal, overhead, markup, contingency, total."""

    def _make_estimate(self, markup=15, overhead=10, contingency=5):
        est = Estimate(
            client_id=self.client_obj.id, name='Test Estimate',
            markup_pct=Decimal(str(markup)),
            overhead_pct=Decimal(str(overhead)),
            contingency_pct=Decimal(str(contingency)),
            created_by_user_id=self.user.id,
        )
        db.session.add(est)
        db.session.flush()
        return est

    def test_line_item_extended_cost_with_waste(self):
        """extended_cost = qty * unit_cost * (1 + waste/100)."""
        est = self._make_estimate()
        li = EstimateLineItem(
            estimate_id=est.id, cost_code_id=self.cc_site.id,
            description='Excavation', unit='CY',
            qty=Decimal('100'), unit_cost=Decimal('50.00'),
            waste_pct=Decimal('10.00'),
            labor_pct=Decimal('60'), material_pct=Decimal('40'),
        )
        db.session.add(li)
        db.session.commit()

        self.assertEqual(li.base_extended, Decimal('5000.00'))
        self.assertEqual(li.waste_amount, Decimal('500.00'))
        self.assertEqual(li.extended_cost, Decimal('5500.00'))
        self.assertEqual(li.labor_amount, Decimal('3300.00'))
        self.assertEqual(li.material_amount, Decimal('2200.00'))

    def test_estimate_total_with_markups(self):
        """total = subtotal * (1 + overhead + markup + contingency)."""
        est = self._make_estimate(markup=15, overhead=10, contingency=5)
        li = EstimateLineItem(
            estimate_id=est.id, cost_code_id=self.cc_found.id,
            description='Foundation', unit='SF',
            qty=Decimal('1000'), unit_cost=Decimal('10.00'),
            waste_pct=Decimal('0'),
            labor_pct=Decimal('50'), material_pct=Decimal('50'),
        )
        db.session.add(li)
        db.session.commit()

        self.assertEqual(est.subtotal, Decimal('10000.00'))
        self.assertEqual(est.overhead_amount, Decimal('1000.00'))
        self.assertEqual(est.markup_amount, Decimal('1500.00'))
        self.assertEqual(est.contingency_amount, Decimal('500.00'))
        self.assertEqual(est.total, Decimal('13000.00'))

    def test_estimate_zero_line_items(self):
        est = self._make_estimate()
        db.session.commit()
        self.assertEqual(est.subtotal, Decimal('0'))
        self.assertEqual(est.total, Decimal('0'))


class TestInvoiceRecalculate(CostMathBase):
    """Invoice.recalculate computes totals from line items and payments."""

    def _make_invoice(self, retainage_pct=0):
        import secrets
        est = Estimate(
            client_id=self.client_obj.id, name='E',
            markup_pct=0, overhead_pct=0, contingency_pct=0,
            created_by_user_id=self.user.id,
        )
        db.session.add(est)
        db.session.flush()

        prop = Proposal(
            estimate_id=est.id, client_id=self.client_obj.id,
            share_token=secrets.token_urlsafe(32),
            created_by_user_id=self.user.id,
        )
        db.session.add(prop)
        db.session.flush()

        contract = Contract(
            proposal_id=prop.id, client_id=self.client_obj.id,
            estimate_id=est.id, share_token=secrets.token_urlsafe(32),
            contract_number='C-001', total_price=Decimal('100000'),
            created_by_user_id=self.user.id,
        )
        db.session.add(contract)
        db.session.flush()

        inv = Invoice(
            contract_id=contract.id, client_id=self.client_obj.id,
            invoice_number='INV-001',
            share_token=secrets.token_urlsafe(32),
            retainage_pct=Decimal(str(retainage_pct)),
            created_by_user_id=self.user.id,
        )
        db.session.add(inv)
        db.session.flush()
        return inv

    def test_simple_recalculate(self):
        inv = self._make_invoice()
        li1 = InvoiceLineItem(invoice_id=inv.id, description='Foundation',
                              amount=Decimal('25000'), sort_order=1)
        li2 = InvoiceLineItem(invoice_id=inv.id, description='Framing',
                              amount=Decimal('15000'), sort_order=2)
        db.session.add_all([li1, li2])
        db.session.commit()

        inv.recalculate()
        self.assertEqual(inv.subtotal, Decimal('40000'))
        self.assertEqual(inv.total_due, Decimal('40000'))
        self.assertEqual(inv.balance_due, Decimal('40000'))

    def test_recalculate_with_retainage(self):
        inv = self._make_invoice(retainage_pct=10)
        li = InvoiceLineItem(invoice_id=inv.id, description='Work',
                             amount=Decimal('50000'), sort_order=1)
        db.session.add(li)
        db.session.commit()

        inv.recalculate()
        self.assertEqual(inv.subtotal, Decimal('50000'))
        self.assertEqual(inv.retainage_amount, Decimal('5000.00'))
        self.assertEqual(inv.total_due, Decimal('45000.00'))

    def test_recalculate_with_payment(self):
        inv = self._make_invoice()
        li = InvoiceLineItem(invoice_id=inv.id, description='Work',
                             amount=Decimal('10000'), sort_order=1)
        pmt = Payment(
            invoice_id=inv.id, client_id=self.client_obj.id,
            amount=Decimal('10000'), method='check', status='succeeded',
        )
        db.session.add_all([li, pmt])
        db.session.commit()

        inv.recalculate()
        self.assertEqual(inv.amount_paid, Decimal('10000'))
        self.assertEqual(inv.balance_due, Decimal('0'))
        self.assertEqual(inv.status, 'Paid')

    def test_partial_payment_sets_partial_status(self):
        inv = self._make_invoice()
        li = InvoiceLineItem(invoice_id=inv.id, description='Work',
                             amount=Decimal('10000'), sort_order=1)
        pmt = Payment(
            invoice_id=inv.id, client_id=self.client_obj.id,
            amount=Decimal('3000'), method='check', status='succeeded',
        )
        db.session.add_all([li, pmt])
        db.session.commit()

        inv.recalculate()
        self.assertEqual(inv.status, 'Partial')
        self.assertEqual(inv.balance_due, Decimal('7000'))

    def test_failed_payment_ignored(self):
        inv = self._make_invoice()
        li = InvoiceLineItem(invoice_id=inv.id, description='Work',
                             amount=Decimal('10000'), sort_order=1)
        pmt = Payment(
            invoice_id=inv.id, client_id=self.client_obj.id,
            amount=Decimal('10000'), method='stripe', status='failed',
        )
        db.session.add_all([li, pmt])
        db.session.commit()

        inv.recalculate()
        self.assertEqual(inv.amount_paid, Decimal('0'))
        self.assertEqual(inv.balance_due, Decimal('10000'))


class TestChangeOrderMath(CostMathBase):
    """ChangeOrder.item_total aggregation."""

    def test_item_total(self):
        co = ChangeOrder(
            client_id=self.client_obj.id, project_id=self.project.id,
            co_number='CO-001', title='Extra window',
            price_to_client=Decimal('5000'),
            created_by_user_id=self.user.id,
        )
        db.session.add(co)
        db.session.flush()

        items = [
            ChangeOrderItem(change_order_id=co.id, description='Window unit',
                            amount=Decimal('2500'), sort_order=1),
            ChangeOrderItem(change_order_id=co.id, description='Install labor',
                            amount=Decimal('1500'), sort_order=2),
        ]
        db.session.add_all(items)
        db.session.commit()

        self.assertEqual(co.item_total, Decimal('4000'))

    def test_empty_change_order(self):
        co = ChangeOrder(
            client_id=self.client_obj.id, project_id=self.project.id,
            co_number='CO-002', title='TBD',
            price_to_client=Decimal('0'),
            created_by_user_id=self.user.id,
        )
        db.session.add(co)
        db.session.commit()
        self.assertEqual(co.item_total, Decimal('0'))


class TestClientContractValue(CostMathBase):
    """Client.total_contract_value sums all project contract values."""

    def test_multi_project_contract_value(self):
        p2 = Project(
            client_id=self.client_obj.id, name='Second ADU',
            contract_value=Decimal('150000'), status='Planning',
        )
        db.session.add(p2)
        db.session.commit()

        # project (250000) + p2 (150000) = 400000
        self.assertEqual(self.client_obj.total_contract_value, Decimal('400000'))

    def test_none_contract_value_treated_as_zero(self):
        p2 = Project(
            client_id=self.client_obj.id, name='No Value',
            contract_value=None, status='Planning',
        )
        db.session.add(p2)
        db.session.commit()

        self.assertEqual(self.client_obj.total_contract_value, Decimal('250000'))


if __name__ == '__main__':
    unittest.main()
