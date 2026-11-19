"""Restrict native reporting sources; do not replace accounting calculations."""
import operator
from odoo import api, models
from odoo.fields import Domain
from odoo.tools import SQL
from .access import can_access


class Report(models.Model):
    _inherit = 'account.report'

    def _get_options_domain(self, options, date_scope):
        domain = Domain(super()._get_options_domain(options, date_scope))
        if not can_access(self.env):
            domain &= Domain('move_id.restricted_accounting', '=', False)
        return domain


class InvoiceAnalysis(models.Model):
    _inherit = 'account.invoice.report'

    def _where(self):
        result = super()._where()
        if can_access(self.env):
            return result
        # This native report builds its SQL table query per environment.
        self.env['account.move'].flush_model(['restricted_accounting'])
        return SQL('%s AND NOT COALESCE(move.restricted_accounting, FALSE)', result)


class Partner(models.Model):
    _inherit = 'res.partner'

    @api.depends_context('uid', 'company')
    def _credit_debit_get(self):
        if can_access(self.env):
            return super()._credit_debit_get()
        self.credit = 0
        self.debit = 0
        # The native implementation bypasses record rules. Preserve its scope
        # and arithmetic, but explicitly exclude restricted entries here.
        rows = self.env['account.move.line'].sudo()._read_group([
            ('restricted_accounting', '=', False),
            ('parent_state', '=', 'posted'),
            ('company_id', 'child_of', self.env.company.root_id.id),
            ('partner_id', 'in', self.ids), ('reconciled', '=', False),
            ('account_id.account_type', 'in', ['asset_receivable', 'liability_payable']),
        ], ['partner_id', 'account_id'], ['amount_residual:sum'])
        for partner, account, amount in rows:
            target = self.browse(partner.id)
            if account.account_type == 'asset_receivable':
                target.credit += amount
            else:
                target.debit -= amount

    def _asset_difference_search(self, account_type, comparison, operand):
        if can_access(self.env):
            return super()._asset_difference_search(account_type, comparison, operand)
        comparisons = {'<': operator.lt, '=': operator.eq, '>': operator.gt,
                       '>=': operator.ge, '<=': operator.le}
        if comparison not in comparisons or not isinstance(operand, (int, float)):
            return []
        rows = self.env['account.move.line'].sudo()._read_group([
            ('restricted_accounting', '=', False),
            ('account_id.account_type', '=', account_type), ('account_id.active', '=', True),
            ('parent_state', '=', 'posted'),
            ('company_id', 'child_of', self.env.company.root_id.id),
        ], ['partner_id'], ['amount_residual:sum'])
        sign = -1 if account_type == 'liability_payable' else 1
        return [('id', 'in', [partner.id for partner, amount in rows
                             if partner and comparisons[comparison](sign * amount, operand)])]

    @api.depends_context('uid', 'company')
    def _invoice_total(self):
        return super()._invoice_total()

    @api.depends_context('uid')
    def _compute_account_move_count(self):
        return super()._compute_account_move_count()

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_supplier_invoice_count(self):
        return super()._compute_supplier_invoice_count()

    @api.depends_context('uid', 'company')
    def _compute_days_sales_outstanding(self):
        return super()._compute_days_sales_outstanding()
