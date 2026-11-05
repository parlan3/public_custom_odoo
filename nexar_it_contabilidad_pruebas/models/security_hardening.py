import operator as comparison_operators

from odoo import api, fields, models, Command, SUPERUSER_ID, _
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.tools import SQL


def visibility(env, path):
    # sudo() retains uid. Internal elevated calculations must retain CDP isolation.
    if env.uid == SUPERUSER_ID:
        return Domain.TRUE
    return Domain(path, '=', False) | Domain(path + '.user_id', '=', env.uid)


def protect_metadata(env, vals):
    if not env.su and {'cdp_circuit_id', 'cdp_user_id', 'cdp_role'} & vals.keys():
        raise AccessError(_('La clasificación y el titular CDP se determinan en el servidor.'))


class Move(models.Model):
    _inherit = 'account.move'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & visibility(self.env, 'journal_id.cdp_circuit_id'), *args, **kwargs)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        return super().write(vals)


class MoveLine(models.Model):
    _inherit = 'account.move.line'

    def _search(self, domain, *args, **kwargs):
        return super()._search(Domain(domain) & visibility(self.env, 'move_id.journal_id.cdp_circuit_id'), *args, **kwargs)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        return super().write(vals)


class Payment(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        return super().write(vals)


class Journal(models.Model):
    _inherit = 'account.journal'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        return super().write(vals)


class Account(models.Model):
    _inherit = 'account.account'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        return super().write(vals)


class InvoiceAnalysis(models.Model):
    _inherit = 'account.invoice.report'

    def _where(self):
        where = super()._where()
        if self.env.uid == SUPERUSER_ID:
            return where
        return SQL(
            '%s AND EXISTS (SELECT 1 FROM account_journal cdp_j '
            'LEFT JOIN nexar_test_circuit cdp_c ON cdp_c.id = cdp_j.cdp_circuit_id '
            'WHERE cdp_j.id = move.journal_id AND (cdp_c.id IS NULL OR cdp_c.user_id = %s))',
            where, self.env.uid,
        )


class Partner(models.Model):
    _inherit = 'res.partner'

    @api.depends_context('company', 'uid')
    def _credit_debit_get(self):
        # The standard implementation uses bypass_access=True. MoveLine._search
        # adds ownership independently of ACLs and record-rule bypass flags.
        return super()._credit_debit_get()

    @api.depends_context('company', 'uid')
    def _invoice_total(self):
        return super()._invoice_total()

    @api.depends_context('uid')
    def _compute_account_move_count(self):
        return super()._compute_account_move_count()

    @api.depends_context('allowed_company_ids', 'uid')
    def _compute_supplier_invoice_count(self):
        return super()._compute_supplier_invoice_count()

    @api.depends_context('company', 'uid')
    def _compute_days_sales_outstanding(self):
        return super()._compute_days_sales_outstanding()

    def _asset_difference_search(self, account_type, operator, operand):
        comparisons = {'<': comparison_operators.lt, '=': comparison_operators.eq,
                       '>': comparison_operators.gt, '>=': comparison_operators.ge,
                       '<=': comparison_operators.le}
        if operator not in comparisons or not isinstance(operand, (float, int)):
            return []
        rows = self.env['account.move.line'].sudo()._read_group([
            ('account_id.account_type', '=', account_type),
            ('account_id.active', '=', True), ('parent_state', '=', 'posted'),
            ('company_id', 'child_of', self.env.company.root_id.id),
        ], ['partner_id'], ['amount_residual:sum'])
        sign = -1 if account_type == 'liability_payable' else 1
        ids = [partner.id for partner, residual in rows
               if partner and comparisons[operator](sign * residual, operand)]
        return [('id', 'in', ids)]


class PartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ids = [vals.get(key) or self.env.context.get('default_' + key)
                   for key in ('debit_move_id', 'credit_move_id')]
            lines = self.env['account.move.line'].browse([record_id for record_id in ids if record_id])
            lines.check_access('write')
        return super().create(vals_list)

    def write(self, vals):
        ids = [vals[key] for key in ('debit_move_id', 'credit_move_id') if vals.get(key)]
        self.env['account.move.line'].browse(ids).check_access('write')
        return super().write(vals)


class FullReconcile(models.Model):
    _inherit = 'account.full.reconcile'

    cdp_circuit_id = fields.Many2one('nexar.test.circuit', readonly=True, copy=False, index=True, ondelete='restrict')
    cdp_user_id = fields.Many2one(related='cdp_circuit_id.user_id', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            protect_metadata(self.env, vals)
            ids = []
            for command in vals.get('reconciled_line_ids', []):
                if command[0] == Command.LINK:
                    ids.append(command[1])
                elif command[0] == Command.SET:
                    ids = list(command[2])
                else:
                    raise ValidationError(_('Usá apuntes existentes para la conciliación.'))
            lines = self.env['account.move.line'].browse(ids)
            lines.check_access('write')
            circuits = lines.cdp_circuit_id
            if len(circuits) > 1 or (circuits and any(not line.cdp_circuit_id for line in lines)):
                raise ValidationError(_('La conciliación debe permanecer dentro del mismo circuito.'))
            prepared.append(dict(vals, cdp_circuit_id=circuits.id if circuits else False))
        # Core removes line commands before creating the record and links lines
        # with SQL afterwards. Set ownership first so create rules can enforce it.
        return super().create(prepared)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if {'reconciled_line_ids', 'partial_reconcile_ids'} & vals.keys():
            raise AccessError(_('Las conciliaciones completas se generan desde sus apuntes.'))
        return super().write(vals)
