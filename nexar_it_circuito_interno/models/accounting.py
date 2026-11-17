from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from .circuit import GROUP


def protect_metadata(env, vals):
    if not env.su and {'ni_circuit_id', 'ni_user_id', 'ni_role'} & vals.keys():
        raise AccessError(_('La pertenencia al circuito se asigna desde el asistente.'))


def check_same_circuit(records):
    circuits = records.mapped('move_id.journal_id.ni_circuit_id')
    if circuits and (len(circuits) != 1 or any(not r.move_id.journal_id.ni_circuit_id for r in records)):
        raise ValidationError(_('Los apuntes deben pertenecer al mismo circuito interno.'))
    return circuits


class Account(models.Model):
    _inherit = 'account.account'
    ni_circuit_id = fields.Many2one('nexar.internal.circuit', string='Circuito interno', readonly=True, copy=False, index=True, ondelete='restrict')
    ni_user_id = fields.Many2one(related='ni_circuit_id.user_id', string='Usuario titular', store=True, index=True)
    ni_role = fields.Char(string='Funci\u00f3n de la cuenta', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        if not self.env.su and self.env.user.has_group(GROUP):
            raise AccessError(_('Las cuentas internas se configuran desde el asistente.'))
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if not self.env.su and self.ni_circuit_id:
            raise AccessError(_('La configuraci\u00f3n de cuentas internas requiere el administrador.'))
        return super().write(vals)

    def unlink(self):
        if self.ni_circuit_id:
            raise AccessError(_('Conserv\u00e1 las cuentas del circuito.'))
        return super().unlink()


class Journal(models.Model):
    _inherit = 'account.journal'
    ni_circuit_id = fields.Many2one('nexar.internal.circuit', string='Circuito interno', readonly=True, copy=False, index=True, ondelete='restrict')
    ni_user_id = fields.Many2one(related='ni_circuit_id.user_id', string='Usuario titular', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        if not self.env.su and self.env.user.has_group(GROUP):
            raise AccessError(_('Los diarios internos se configuran desde el asistente.'))
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        fixed = {'company_id', 'code', 'type', 'currency_id', 'default_account_id',
                 'suspense_account_id', 'profit_account_id', 'loss_account_id',
                 'l10n_latam_use_documents', 'l10n_ar_afip_pos_number', 'l10n_ar_afip_pos_system'}
        if not self.env.su and self.ni_circuit_id and fixed & vals.keys():
            raise AccessError(_('La configuraci\u00f3n del diario interno requiere el administrador.'))
        return super().write(vals)

    @api.constrains('ni_circuit_id', 'company_id', 'l10n_latam_use_documents',
                    'l10n_ar_afip_pos_number', 'default_account_id', 'suspense_account_id',
                    'profit_account_id', 'loss_account_id')
    def _check_internal_journal(self):
        for journal in self.filtered('ni_circuit_id'):
            if (journal.company_id != journal.ni_circuit_id.company_id
                    or journal.l10n_latam_use_documents or journal.l10n_ar_afip_pos_number):
                raise ValidationError(_('El diario interno debe usar su compa\u00f1\u00eda y carecer de punto de venta ARCA.'))
            accounts = (journal.default_account_id | journal.suspense_account_id
                        | journal.profit_account_id | journal.loss_account_id)
            if any(a.ni_circuit_id != journal.ni_circuit_id for a in accounts):
                raise ValidationError(_('Las cuentas del diario deben pertenecer a su circuito.'))


class Move(models.Model):
    _inherit = 'account.move'
    ni_circuit_id = fields.Many2one(related='journal_id.ni_circuit_id', string='Circuito interno', store=True, index=True)
    ni_user_id = fields.Many2one(related='journal_id.ni_user_id', string='Usuario titular', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        internal = self.env.user.has_group(GROUP)
        return super(Move, self.with_context(
            mail_create_nosubscribe=True, mail_auto_subscribe_no_notify=True,
        ) if internal else self).create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if 'journal_id' in vals:
            target = self.env['account.journal'].browse(vals['journal_id'])
            target.check_access('read')
            if any(m.ni_circuit_id != target.ni_circuit_id for m in self):
                raise ValidationError(_('No se pueden trasladar movimientos entre circuitos.'))
        return super().write(vals)

    @api.depends('partner_id', 'partner_shipping_id', 'company_id', 'move_type', 'journal_id')
    def _compute_fiscal_position_id(self):
        internal = self.filtered(lambda m: m.journal_id.ni_circuit_id)
        internal.fiscal_position_id = False
        super(Move, self - internal)._compute_fiscal_position_id()

    @api.constrains('journal_id', 'company_id', 'currency_id', 'fiscal_position_id',
                    'invoice_cash_rounding_id')
    def _check_internal_move(self):
        for move in self.filtered('ni_circuit_id'):
            if move.company_id != move.ni_circuit_id.company_id:
                raise ValidationError(_('Compa\u00f1\u00eda incompatible con el circuito.'))
            if move.currency_id.name not in ('ARS', 'USD'):
                raise ValidationError(_('El circuito admite ARS y USD.'))
            if move.fiscal_position_id or move.invoice_cash_rounding_id:
                raise ValidationError(_('El circuito interno utiliza posici\u00f3n fiscal y redondeo vac\u00edos.'))

    def _ea_check_analytic_distribution(self):
        # This site's analytic control applies to its ordinary accounting.
        # Internal lines explicitly prohibit analytic allocation.
        ordinary = self.filtered(lambda move: not move.ni_circuit_id)
        if ordinary:
            return super(Move, ordinary)._ea_check_analytic_distribution()
        return True

    def _post(self, soft=True):
        self.check_access('write')
        self._check_internal_move()
        self.line_ids._check_internal_lines()
        return super()._post(soft=soft)

    def _portal_ensure_token(self):
        if self.ni_circuit_id:
            raise AccessError(_('Los documentos internos son privados.'))
        return super()._portal_ensure_token()

    def _message_auto_subscribe_followers(self, updated_values, default_subtype_ids):
        if self.ni_circuit_id:
            return []
        return super()._message_auto_subscribe_followers(updated_values, default_subtype_ids)

    def message_subscribe(self, partner_ids=None, subtype_ids=None):
        if self.ni_circuit_id:
            raise AccessError(_('Los documentos internos no admiten suscriptores.'))
        return super().message_subscribe(partner_ids=partner_ids, subtype_ids=subtype_ids)

    def message_post(self, **kwargs):
        if self.ni_circuit_id:
            if kwargs.get('partner_ids'):
                raise AccessError(_('Los mensajes internos no admiten destinatarios.'))
            kwargs.update(message_type='comment', subtype_xmlid='mail.mt_note')
        return super().message_post(**kwargs)


class Line(models.Model):
    _inherit = 'account.move.line'
    ni_circuit_id = fields.Many2one(related='move_id.ni_circuit_id', string='Circuito interno', store=True, index=True)
    ni_user_id = fields.Many2one(related='move_id.ni_user_id', string='Usuario titular', store=True, index=True)

    @api.depends('product_id', 'partner_id', 'move_id.move_type', 'move_id.journal_id', 'display_type')
    def _compute_account_id(self):
        internal = self.filtered(lambda l: l.move_id.journal_id.ni_circuit_id)
        # Do not compute native partner/product accounts first: they are inaccessible to the owner.
        super(Line, self - internal)._compute_account_id()
        for line in internal:
            circuit = line.move_id.journal_id.ni_circuit_id
            sale = line.move_id.is_sale_document(include_receipts=True)
            if line.display_type in ('line_section', 'line_subsection', 'line_note'):
                line.account_id = False
            elif line.display_type == 'payment_term':
                line.account_id = circuit._account('receivable' if sale else 'payable')
            elif line.move_id.is_invoice(include_receipts=True):
                line.account_id = circuit._account('income' if sale else 'expense')
            elif not line.account_id:
                line.account_id = line.move_id.journal_id.default_account_id

    @api.depends('product_id', 'product_uom_id', 'move_id.journal_id')
    def _compute_tax_ids(self):
        internal = self.filtered(lambda l: l.move_id.journal_id.ni_circuit_id)
        internal.tax_ids = False
        super(Line, self - internal)._compute_tax_ids()

    @api.depends('account_id', 'partner_id', 'product_id', 'move_id.journal_id')
    def _compute_analytic_distribution(self):
        internal = self.filtered(lambda line: line.move_id.journal_id.ni_circuit_id)
        # Company-wide distribution models must not populate the private circuit.
        internal.analytic_distribution = False
        super(Line, self - internal)._compute_analytic_distribution()

    @api.constrains('account_id', 'move_id', 'tax_ids', 'tax_line_id', 'tax_tag_ids', 'analytic_distribution')
    def _check_internal_lines(self):
        for line in self:
            circuit = line.move_id.journal_id.ni_circuit_id
            if line.account_id and line.account_id.ni_circuit_id != circuit:
                raise ValidationError(_('La cuenta y el diario deben pertenecer al mismo circuito.'))
            if circuit and (line.tax_ids or line.tax_line_id or line.tax_tag_ids or line.analytic_distribution):
                raise ValidationError(_('El circuito utiliza l\u00edneas sin impuestos, etiquetas fiscales ni anal\u00edtica.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            protect_metadata(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        protect_metadata(self.env, vals)
        if 'move_id' in vals:
            target = self.env['account.move'].browse(vals['move_id'])
            target.check_access('read')
            if any(line.ni_circuit_id != target.ni_circuit_id for line in self):
                raise ValidationError(_('No se pueden trasladar apuntes entre circuitos.'))
        return super().write(vals)

    def _validate_analytic_distribution(self):
        ordinary = self.filtered(lambda line: not line.move_id.journal_id.ni_circuit_id)
        return super(Line, ordinary)._validate_analytic_distribution()

    def _get_exchange_journal(self, company):
        circuit = check_same_circuit(self)
        if circuit:
            return circuit._journal('INTFX')
        return super()._get_exchange_journal(company)

    def _get_exchange_account(self, company, amount):
        circuit = check_same_circuit(self)
        if circuit:
            return circuit._account('fx_loss' if amount > 0 else 'fx_gain')
        return super()._get_exchange_account(company, amount)

    @api.model
    def _create_exchange_difference_moves(self, exchange_diff_values_list):
        internal_values, normal_values = [], []
        for values in exchange_diff_values_list:
            journal = self.env['account.journal'].browse(values['move_values']['journal_id'])
            (internal_values if journal.ni_circuit_id else normal_values).append(values)
        moves = super()._create_exchange_difference_moves(normal_values)
        # Native creation checks the company's fiscal FX accounts even when an internal
        # journal was selected. Create the already prepared internal values separately.
        if internal_values:
            internal_moves = self.env['account.move'].with_context(
                no_exchange_difference=True, move_reverse_cancel=False,
            ).create([v['move_values'] for v in internal_values])
            to_post = self.env['account.move']
            for move, values in zip(internal_moves, internal_values):
                if values['to_post']:
                    to_post |= move
            to_post.with_context(validate_analytic=False)._post(soft=False)
            moves |= internal_moves
        return moves

    def reconcile(self):
        self.check_access('write')
        check_same_circuit(self)
        return super().reconcile()


class Send(models.AbstractModel):
    _inherit = 'account.move.send'

    def _generate_and_send_invoices(self, moves, *args, **kwargs):
        if moves.ni_circuit_id:
            raise AccessError(_('El circuito interno no permite enviar comprobantes.'))
        return super()._generate_and_send_invoices(moves, *args, **kwargs)


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    def _ni_check_private_attachment(self):
        for attachment in self:
            if attachment.res_model in ('account.move', 'account.payment', 'account.journal', 'account.account') and attachment.res_id:
                record = self.env[attachment.res_model].sudo().browse(attachment.res_id).exists()
                if record.ni_circuit_id and (attachment.public or attachment.access_token):
                    raise AccessError(_('Los adjuntos internos no pueden tener acceso p\u00fablico ni token.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ni_check_private_attachment()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._ni_check_private_attachment()
        return result


class SharedPartner(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        if (not self.env.su and self.env.user.has_group(GROUP)
                and {'property_account_receivable_id', 'property_account_payable_id',
                     'property_account_position_id'} & vals.keys()):
            raise AccessError(_('Las cuentas compartidas de contactos se administran fuera del circuito.'))
        return super().write(vals)
