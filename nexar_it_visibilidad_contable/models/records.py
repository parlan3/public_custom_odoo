from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from .access import OPERATOR


def validate_shared_attachments(env, model, ids):
    if ids and env['ir.attachment'].sudo().search_count([
        ('res_model','=',model), ('res_id','in',ids), '|', ('public','=',True), ('access_token','!=',False)
    ], limit=1):
        raise ValidationError(_('Revocá los enlaces públicos de los adjuntos antes de restringir estos registros.'))


class DerivedRestriction(models.AbstractModel):
    _name = 'nexar.accounting.restriction'
    _description = 'Clasificación de acceso a registros contables'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any('restricted_accounting' in vals for vals in vals_list):
            raise AccessError(_('La restricción se obtiene del diario y las cuentas; no puede cambiarse en el movimiento.'))
        records = super().create(vals_list)
        records._check_restricted_operation()
        records._check_no_public_restricted_access()
        return records

    def write(self, vals):
        self._check_restricted_operation()
        if 'restricted_accounting' in vals and not self.env.su:
            raise AccessError(_('La restricción se obtiene del diario y las cuentas; no puede cambiarse en el movimiento.'))
        result = super().write(vals)
        # Native write rules check the source state. Also protect an ordinary
        # entry changed to a restricted journal/account during this write.
        self._check_restricted_operation()
        if {'journal_id','line_ids','account_id','access_token'} & vals.keys():
            self._check_no_public_restricted_access()
        return result

    def _check_restricted_operation(self):
        if not self.env.su and not self.env.user.has_group(OPERATOR) and any(self.mapped('restricted_accounting')):
            raise AccessError(_('No tenés permiso para modificar el circuito restringido.'))

    def _check_no_public_restricted_access(self):
        restricted = self.filtered('restricted_accounting')
        if 'access_token' in self._fields and any(restricted.mapped('access_token')):
            raise ValidationError(_('Revocá los enlaces públicos del documento antes de restringirlo.'))
        validate_shared_attachments(self.env, self._name, restricted.ids)


class Move(models.Model):
    _name = 'account.move'
    _inherit = ['account.move','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('journal_id.restricted_accounting','line_ids.account_id.restricted_accounting')
    def _compute_accounting_restriction(self):
        for move in self:
            move.restricted_accounting = move.journal_id.restricted_accounting or any(move.line_ids.account_id.mapped('restricted_accounting'))

    def _portal_ensure_token(self):
        if any(self.mapped('restricted_accounting')):
            raise AccessError(_('Los documentos del circuito restringido no admiten enlaces públicos.'))
        return super()._portal_ensure_token()


class Line(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(related='move_id.restricted_accounting', store=True, index=True)


class Payment(models.Model):
    _name = 'account.payment'
    _inherit = ['account.payment','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('journal_id.restricted_accounting','move_id.restricted_accounting','destination_account_id.restricted_accounting')
    def _compute_accounting_restriction(self):
        for record in self:
            record.restricted_accounting = bool(record.journal_id.restricted_accounting or record.move_id.restricted_accounting or record.destination_account_id.restricted_accounting)


class PaymentMethod(models.Model):
    _name = 'account.payment.method.line'
    _inherit = ['account.payment.method.line','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('journal_id.restricted_accounting','payment_account_id.restricted_accounting')
    def _compute_accounting_restriction(self):
        for record in self:
            record.restricted_accounting = bool(record.journal_id.restricted_accounting or record.payment_account_id.restricted_accounting)


class Partial(models.Model):
    _name = 'account.partial.reconcile'
    _inherit = ['account.partial.reconcile','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('debit_move_id.restricted_accounting','credit_move_id.restricted_accounting')
    def _compute_accounting_restriction(self):
        for record in self:
            record.restricted_accounting = bool(record.debit_move_id.restricted_accounting or record.credit_move_id.restricted_accounting)


class Full(models.Model):
    _name = 'account.full.reconcile'
    _inherit = ['account.full.reconcile','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('reconciled_line_ids.restricted_accounting')
    def _compute_accounting_restriction(self):
        for record in self:
            record.restricted_accounting = any(record.reconciled_line_ids.mapped('restricted_accounting'))


class Statement(models.Model):
    _name = 'account.bank.statement'
    _inherit = ['account.bank.statement','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(compute='_compute_accounting_restriction', store=True, index=True, copy=False)

    @api.depends('journal_id.restricted_accounting','line_ids.move_id.restricted_accounting')
    def _compute_accounting_restriction(self):
        for record in self:
            record.restricted_accounting = bool(record.journal_id.restricted_accounting or any(record.line_ids.move_id.mapped('restricted_accounting')))


class StatementLine(models.Model):
    _name = 'account.bank.statement.line'
    _inherit = ['account.bank.statement.line','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(related='move_id.restricted_accounting', store=True, index=True)


class AnalyticLine(models.Model):
    _name = 'account.analytic.line'
    _inherit = ['account.analytic.line','nexar.accounting.restriction']
    restricted_accounting = fields.Boolean(related='move_line_id.restricted_accounting', store=True, index=True)


class MoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    def _check_move_constrains(self, moves):
        if any(moves.mapped('restricted_accounting')):
            raise AccessError(_('El envío externo de documentos restringidos no está habilitado.'))
        return super()._check_move_constrains(moves)
