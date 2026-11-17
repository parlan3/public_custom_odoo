import operator
from odoo import api, models, SUPERUSER_ID
from odoo.fields import Domain
from odoo.tools import SQL
from .circuit import GROUP


def scope(env, path):
    # sudo() keeps uid. Preserve visibility in elevated ORM computations.
    if env.uid == SUPERUSER_ID:
        return Domain.TRUE
    if env.user.has_group(GROUP):
        return Domain(path + '.user_id', '=', env.uid)
    return Domain(path, '=', False)


class MoveVisibility(models.Model):
    _inherit = 'account.move'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & scope(self.env, 'journal_id.ni_circuit_id'), *args, **kwargs)


class LineVisibility(models.Model):
    _inherit = 'account.move.line'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & scope(self.env, 'move_id.journal_id.ni_circuit_id'), *args, **kwargs)


class PaymentVisibility(models.Model):
    _inherit = 'account.payment'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & scope(self.env, 'journal_id.ni_circuit_id'), *args, **kwargs)


class AccountVisibility(models.Model):
    _inherit = 'account.account'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & scope(self.env, 'ni_circuit_id'), *args, **kwargs)


class JournalVisibility(models.Model):
    _inherit = 'account.journal'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & scope(self.env, 'ni_circuit_id'), *args, **kwargs)


class InvoiceAnalysis(models.Model):
    _inherit = 'account.invoice.report'

    def _where(self):
        result = super()._where()
        if self.env.uid == SUPERUSER_ID:
            return result
        clause = (SQL('ci.user_id = %s', self.env.uid) if self.env.user.has_group(GROUP)
                  else SQL('j.ni_circuit_id IS NULL'))
        return SQL(
            '%s AND EXISTS (SELECT 1 FROM account_journal j '
            'LEFT JOIN nexar_internal_circuit ci ON ci.id = j.ni_circuit_id '
            'WHERE j.id = move.journal_id AND %s)', result, clause)


class Report(models.Model):
    _inherit = 'account.report'

    def _get_options_domain(self, options, date_scope):
        domain = super()._get_options_domain(options, date_scope)
        # User options cannot request another owner's circuit.
        return Domain(domain) & scope(self.env, 'move_id.journal_id.ni_circuit_id')


class Partner(models.Model):
    _inherit = 'res.partner'

    @api.depends_context('uid', 'company')
    def _credit_debit_get(self):
        return super()._credit_debit_get()

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

    def _asset_difference_search(self, account_type, comparison, operand):
        comparisons = {'<': operator.lt, '=': operator.eq, '>': operator.gt,
                       '>=': operator.ge, '<=': operator.le}
        if comparison not in comparisons or not isinstance(operand, (int, float)):
            return []
        rows = self.env['account.move.line'].sudo()._read_group([
            ('account_id.account_type', '=', account_type), ('account_id.active', '=', True),
            ('parent_state', '=', 'posted'),
            ('company_id', 'child_of', self.env.company.root_id.id),
        ], ['partner_id'], ['amount_residual:sum'])
        sign = -1 if account_type == 'liability_payable' else 1
        ids = [partner.id for partner, amount in rows
               if partner and comparisons[comparison](sign * amount, operand)]
        return [('id', 'in', ids)]
