from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, ValidationError
from .accounting import protect_metadata, check_same_circuit
from .circuit import GROUP


class Payment(models.Model):
    _inherit = 'account.payment'
    ni_circuit_id = fields.Many2one(related='journal_id.ni_circuit_id', store=True, index=True)
    ni_user_id = fields.Many2one(related='journal_id.ni_user_id', store=True, index=True)

    @api.depends('journal_id', 'partner_id', 'partner_type')
    def _compute_destination_account_id(self):
        internal = self.filtered(lambda p: p.journal_id.ni_circuit_id)
        super(Payment, self - internal)._compute_destination_account_id()
        for payment in internal:
            payment.destination_account_id = payment.journal_id.ni_circuit_id._account(
                'receivable' if payment.partner_type == 'customer' else 'payable')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        target = self.with_context(mail_create_nosubscribe=True, mail_auto_subscribe_no_notify=True) if self.env.user.has_group(GROUP) else self
        return super(Payment, target).create(vals_list)

    def _message_auto_subscribe_followers(self, updated_values, default_subtype_ids):
        if self.ni_circuit_id:
            return []
        return super()._message_auto_subscribe_followers(updated_values, default_subtype_ids)

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        if self.ni_circuit_id:
            raise AccessError(_('Los pagos internos no admiten suscriptores.'))
        return super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids)

    def message_post(self, **kwargs):
        if self.ni_circuit_id:
            if kwargs.get('partner_ids'):
                raise AccessError(_('Los mensajes internos no admiten destinatarios.'))
            kwargs.update(message_type='comment', subtype_xmlid='mail.mt_note')
        return super().message_post(**kwargs)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if 'journal_id' in vals:
            target = self.env['account.journal'].browse(vals['journal_id'])
            target.check_access('read')
            if any(p.ni_circuit_id != target.ni_circuit_id for p in self):
                raise ValidationError(_('No se pueden trasladar pagos entre circuitos.'))
        return super().write(vals)

    @api.constrains('journal_id', 'destination_account_id', 'outstanding_account_id',
                    'currency_id', 'payment_method_line_id')
    def _check_internal_payment(self):
        for payment in self:
            circuit = payment.journal_id.ni_circuit_id
            for account in payment.destination_account_id | payment.outstanding_account_id:
                if account.ni_circuit_id != circuit:
                    raise ValidationError(_('Las cuentas del pago deben pertenecer a su circuito.'))
            if circuit:
                if payment.currency_id != payment.journal_id.currency_id:
                    raise ValidationError(_('ElegÃ­ la caja correspondiente a la moneda del pago.'))
                if payment.payment_method_line_id and payment.payment_method_line_id.code != 'manual':
                    raise ValidationError(_('UsÃ¡ un mÃ©todo manual en el circuito interno.'))

    def action_post(self):
        self.check_access('write')
        self._check_internal_payment()
        return super().action_post()


class MethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    @api.constrains('journal_id', 'payment_account_id', 'payment_method_id')
    def _check_internal_method(self):
        for line in self:
            circuit = line.journal_id.ni_circuit_id
            # Odoo populates payment methods with the company defaults during journal
            # creation. The setup replaces them before granting the operator group.
            if circuit and line.env.su:
                continue
            if line.payment_account_id and line.payment_account_id.ni_circuit_id != circuit:
                raise ValidationError(_('La cuenta del mÃ©todo de pago debe pertenecer al circuito.'))
            if circuit and line.code != 'manual':
                raise ValidationError(_('El circuito requiere pagos manuales.'))


class Register(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('payment_type', 'company_id', 'can_edit_wizard', 'line_ids')
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for wizard in self:
            circuit = check_same_circuit(wizard.line_ids)
            wizard.available_journal_ids = wizard.available_journal_ids.filtered(
                lambda journal: journal.ni_circuit_id == circuit)

    def action_create_payments(self):
        self.line_ids.check_access('write')
        circuit = check_same_circuit(self.line_ids)
        if self.journal_id.ni_circuit_id != circuit:
            raise ValidationError(_('ElegÃ­ una caja del mismo circuito.'))
        return super().action_create_payments()


class Partial(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ids = [vals.get(key) or self.env.context.get('default_' + key)
                   for key in ('debit_move_id', 'credit_move_id')]
            lines = self.env['account.move.line'].browse([i for i in ids if i])
            lines.check_access('write')
            check_same_circuit(lines)
        return super().create(vals_list)

    @api.constrains('debit_move_id', 'credit_move_id')
    def _check_internal_partial(self):
        for rec in self:
            check_same_circuit(rec.debit_move_id | rec.credit_move_id)


class Full(models.Model):
    _inherit = 'account.full.reconcile'
    ni_circuit_id = fields.Many2one('nexar.internal.circuit', readonly=True, copy=False, index=True, ondelete='restrict')
    ni_user_id = fields.Many2one(related='ni_circuit_id.user_id', store=True, index=True)

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
                    raise ValidationError(_('ConciliÃ¡ apuntes existentes.'))
            lines = self.env['account.move.line'].browse(ids)
            lines.check_access('write')
            circuit = check_same_circuit(lines)
            prepared.append(dict(vals, ni_circuit_id=circuit.id or False))
        return super().create(prepared)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if {'reconciled_line_ids', 'partial_reconcile_ids'} & vals.keys():
            raise AccessError(_('Las conciliaciones completas se generan desde sus apuntes.'))
        return super().write(vals)
