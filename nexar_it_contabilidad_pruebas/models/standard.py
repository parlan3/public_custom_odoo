from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain


GROUP = 'nexar_it_contabilidad_pruebas.group_operator'


class Circuit(models.Model):
    _inherit = 'nexar.test.circuit'

    def _initialize_target(self, companies, user):
        super()._initialize_target(companies, user)
        self.sudo().search([('company_id', 'in', companies.ids)])._initialize_standard()
        user.write({'group_ids': [Command.link(self.env.ref('account.group_account_user').id)]})

    def _initialize_standard(self):
        # Private, called from the administrator-only wizard or the upgrade hook.
        for circuit in self.sudo():
            company = circuit.company_id
            account_model = self.env['account.account'].sudo().with_company(company)
            accounts = {}
            for code, name, kind, reconcile in [
                ('01', 'CDP Clientes', 'asset_receivable', True),
                ('02', 'CDP Proveedores', 'liability_payable', True),
                ('03', 'CDP Ingresos', 'income', False),
                ('04', 'CDP Gastos', 'expense', False),
                ('05', 'CDP Caja', 'asset_cash', True),
                ('06', 'CDP Banco', 'asset_cash', True),
                ('07', 'CDP Transitoria', 'asset_current', True),
            ]:
                account = account_model.search([
                    ('cdp_circuit_id', '=', circuit.id), ('cdp_role', '=', code),
                ], limit=1)
                if not account:
                    account = account_model.create({
                        'name': name, 'code': f'CDP{company.id}{code}',
                        'account_type': kind, 'reconcile': reconcile,
                        'company_ids': [Command.set(company.ids)],
                        'cdp_circuit_id': circuit.id, 'cdp_role': code,
                    })
                accounts[code] = account
            for code, name, kind, account_code in [
                ('CDPV', 'CDP Ventas', 'sale', '03'),
                ('CDPC', 'CDP Compras', 'purchase', '04'),
                ('CDPE', 'CDP Caja', 'cash', '05'),
                ('CDPB', 'CDP Banco', 'bank', '06'),
                ('CDPG', 'CDP General', 'general', '07'),
            ]:
                journal = self.env['account.journal'].sudo().search([
                    ('cdp_circuit_id', '=', circuit.id), ('code', '=', code),
                ], limit=1)
                if not journal:
                    journal = self.env['account.journal'].sudo().with_company(company).create({
                        'name': name, 'code': code, 'type': kind,
                        'company_id': company.id, 'cdp_circuit_id': circuit.id,
                        'default_account_id': accounts[account_code].id,
                        'suspense_account_id': accounts['07'].id,
                        'profit_account_id': accounts['03'].id,
                        'loss_account_id': accounts['04'].id,
                        'l10n_latam_use_documents': False,
                    })
                if kind in ('bank', 'cash'):
                    methods = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
                    # Same liquidity account produces an immediately paid invoice.
                    methods.write({'payment_account_id': accounts[account_code].id})
            circuit.user_id.write({'group_ids': [Command.link(self.env.ref('account.group_account_user').id)]})
        for xmlid in ('account_reports.general_ledger_report', 'account_reports.balance_sheet', 'account_reports.profit_and_loss'):
            self.env.ref(xmlid).sudo().write({'filter_journals': True, 'filter_aml_ir_filters': True})

    def _account(self, role):
        self.ensure_one()
        account = self.env['account.account'].search([
            ('cdp_circuit_id', '=', self.id), ('cdp_role', '=', role),
        ], limit=1)
        if not account:
            raise UserError(_('Falta la cuenta CDP requerida. Ejecutá la configuración.'))
        return account


class Account(models.Model):
    _inherit = 'account.account'

    cdp_circuit_id = fields.Many2one('nexar.test.circuit', readonly=True, copy=False, index=True, ondelete='restrict')
    cdp_user_id = fields.Many2one(related='cdp_circuit_id.user_id', store=True, index=True)
    cdp_role = fields.Char(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('cdp_circuit_id') or v.get('cdp_role') for v in vals_list):
            raise AccessError(_('La configuración CDP requiere el asistente de administración.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and {'cdp_circuit_id', 'cdp_role', 'company_ids'} & vals.keys() and (self.cdp_circuit_id or vals.get('cdp_circuit_id')):
            raise AccessError(_('La pertenencia de las cuentas CDP es fija.'))
        return super().write(vals)


class Journal(models.Model):
    _inherit = 'account.journal'

    cdp_circuit_id = fields.Many2one('nexar.test.circuit', readonly=True, copy=False, index=True, ondelete='restrict')
    cdp_user_id = fields.Many2one(related='cdp_circuit_id.user_id', store=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(v.get('cdp_circuit_id') for v in vals_list):
            raise AccessError(_('Usá el asistente de configuración CDP.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and 'cdp_circuit_id' in vals:
            raise AccessError(_('La pertenencia de los diarios CDP es fija.'))
        return super().write(vals)

    @api.constrains('cdp_circuit_id', 'l10n_latam_use_documents', 'company_id', 'default_account_id', 'suspense_account_id')
    def _check_cdp_config(self):
        for journal in self.filtered('cdp_circuit_id'):
            if journal.company_id != journal.cdp_circuit_id.company_id or journal.l10n_latam_use_documents:
                raise ValidationError(_('CDP requiere su compañía y documentos fiscales deshabilitados.'))
            for account in journal.default_account_id | journal.suspense_account_id:
                if account.cdp_circuit_id != journal.cdp_circuit_id:
                    raise ValidationError(_('El diario requiere cuentas del mismo circuito CDP.'))


class Move(models.Model):
    _inherit = 'account.move'

    cdp_circuit_id = fields.Many2one(related='journal_id.cdp_circuit_id', store=True, index=True)
    cdp_user_id = fields.Many2one(related='journal_id.cdp_user_id', store=True, index=True)

    def _search_default_journal(self):
        if self.env.context.get('cdp_entry'):
            journal = self.env['account.journal'].search([
                ('company_id', '=', (self.company_id or self.env.company).id),
                ('cdp_user_id', '=', self.env.uid),
                ('type', 'in', self._get_valid_journal_types()),
            ], limit=1)
            if not journal:
                raise UserError(_('No hay un diario CDP disponible para esta compañía.'))
            return journal
        return super()._search_default_journal()

    @api.depends('move_type', 'company_id', 'journal_id')
    def _compute_suitable_journal_ids(self):
        super()._compute_suitable_journal_ids()
        for move in self:
            if self.env.context.get('cdp_entry') or move.journal_id.cdp_circuit_id:
                move.suitable_journal_ids = move.suitable_journal_ids.filtered(lambda j: j.cdp_user_id.id == self.env.uid)

    @api.depends('partner_id', 'partner_shipping_id', 'company_id', 'journal_id')
    def _compute_fiscal_position_id(self):
        super()._compute_fiscal_position_id()
        for move in self.filtered(lambda m: m.journal_id.cdp_circuit_id):
            move.fiscal_position_id = False

    def write(self, vals):
        if 'journal_id' in vals:
            target = self.env['account.journal'].browse(vals['journal_id'])
            target.check_access('read')
            if any(move.cdp_circuit_id != target.cdp_circuit_id for move in self):
                raise ValidationError(_('No se pueden trasladar comprobantes entre circuitos.'))
        return super().write(vals)

    @api.constrains('currency_id', 'journal_id', 'fiscal_position_id', 'invoice_cash_rounding_id')
    def _check_cdp_move(self):
        for move in self.filtered('cdp_circuit_id'):
            if move.currency_id != move.company_id.currency_id:
                raise ValidationError(_('Esta versión de CDP opera en la moneda de la compañía.'))
            if move.fiscal_position_id or move.invoice_cash_rounding_id:
                raise ValidationError(_('CDP requiere posición fiscal y redondeo fiscal vacíos.'))

    def _post(self, soft=True):
        self.check_access('write')
        self.filtered('cdp_circuit_id')._check_cdp_move()
        self.line_ids._check_cdp_accounts()
        return super()._post(soft=soft)

    def _portal_ensure_token(self):
        if self.cdp_circuit_id:
            raise AccessError(_('Los comprobantes CDP son privados.'))
        return super()._portal_ensure_token()


class MoveLine(models.Model):
    _inherit = 'account.move.line'

    cdp_circuit_id = fields.Many2one(related='move_id.cdp_circuit_id', store=True, index=True)
    cdp_user_id = fields.Many2one(related='move_id.cdp_user_id', store=True, index=True)

    @api.depends('product_id', 'partner_id', 'move_id.move_type', 'move_id.journal_id', 'display_type')
    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self:
            circuit = line.move_id.journal_id.cdp_circuit_id
            if not circuit or line.display_type in ('line_section', 'line_subsection', 'line_note'):
                continue
            if line.display_type == 'payment_term':
                line.account_id = circuit._account('01' if line.move_id.is_sale_document(include_receipts=True) else '02')
            elif line.move_id.is_invoice(include_receipts=True) and line.display_type == 'product':
                if not line.account_id or line.account_id.cdp_circuit_id != circuit:
                    line.account_id = circuit._account('03' if line.move_id.is_sale_document(include_receipts=True) else '04')

    @api.depends('product_id', 'product_uom_id', 'move_id.journal_id')
    def _compute_tax_ids(self):
        super()._compute_tax_ids()
        for line in self.filtered(lambda l: l.move_id.journal_id.cdp_circuit_id):
            line.tax_ids = False

    @api.constrains('account_id', 'move_id', 'tax_ids', 'tax_line_id', 'tax_tag_ids', 'analytic_distribution')
    def _check_cdp_accounts(self):
        for line in self:
            if line.account_id and line.account_id.cdp_circuit_id != line.move_id.journal_id.cdp_circuit_id:
                raise ValidationError(_('La cuenta y el diario deben pertenecer al mismo circuito.'))
            if line.move_id.journal_id.cdp_circuit_id and (line.tax_ids or line.tax_line_id or line.tax_tag_ids or line.analytic_distribution):
                raise ValidationError(_('Esta versión de CDP requiere líneas sin impuestos, etiquetas fiscales ni distribución analítica.'))

    def write(self, vals):
        if 'move_id' in vals and any(line.move_id.id != vals['move_id'] for line in self) and (self.cdp_circuit_id or self.env.user.has_group(GROUP)):
            raise AccessError(_('No se pueden trasladar apuntes entre comprobantes.'))
        return super().write(vals)

    def reconcile(self):
        self.check_access('write')
        circuits = set(self.mapped('move_id.journal_id.cdp_circuit_id').ids)
        if circuits and (len(circuits) != 1 or any(not line.cdp_circuit_id for line in self)):
            raise ValidationError(_('La conciliación debe permanecer dentro del mismo circuito.'))
        return super().reconcile()


class Payment(models.Model):
    _inherit = 'account.payment'

    cdp_circuit_id = fields.Many2one(related='journal_id.cdp_circuit_id', store=True, index=True)
    cdp_user_id = fields.Many2one(related='journal_id.cdp_user_id', store=True, index=True)

    @api.depends('company_id', 'partner_id')
    def _compute_journal_id(self):
        super()._compute_journal_id()
        if self.env.context.get('cdp_entry'):
            for payment in self:
                if not payment.journal_id.cdp_circuit_id or payment.journal_id.company_id != payment.company_id:
                    payment.journal_id = self.env['account.journal'].search([
                        ('company_id', '=', (payment.company_id or self.env.company).id),
                        ('cdp_user_id', '=', self.env.uid), ('type', 'in', ('bank', 'cash')),
                    ], limit=1)

    @api.depends('journal_id', 'partner_id', 'partner_type')
    def _compute_destination_account_id(self):
        super()._compute_destination_account_id()
        for payment in self.filtered(lambda p: p.journal_id.cdp_circuit_id):
            payment.destination_account_id = payment.journal_id.cdp_circuit_id._account('01' if payment.partner_type == 'customer' else '02')

    def write(self, vals):
        if 'journal_id' in vals:
            target = self.env['account.journal'].browse(vals['journal_id'])
            target.check_access('read')
            if any(payment.cdp_circuit_id != target.cdp_circuit_id for payment in self):
                raise ValidationError(_('No se pueden trasladar pagos entre circuitos.'))
        return super().write(vals)

    @api.constrains('journal_id', 'destination_account_id', 'outstanding_account_id', 'currency_id', 'payment_method_line_id')
    def _check_cdp_payment(self):
        for payment in self:
            for account in payment.destination_account_id | payment.outstanding_account_id:
                if account.cdp_circuit_id != payment.journal_id.cdp_circuit_id:
                    raise ValidationError(_('Las cuentas del pago deben pertenecer al mismo circuito.'))
            if payment.cdp_circuit_id:
                if payment.currency_id != payment.company_id.currency_id or payment.payment_method_line_id.code != 'manual':
                    raise ValidationError(_('CDP utiliza pagos manuales en moneda de la compañía.'))

    def action_post(self):
        self.check_access('write')
        self._check_cdp_payment()
        for payment in self.filtered('cdp_circuit_id'):
            if not payment.destination_account_id or not payment.outstanding_account_id:
                raise ValidationError(_('El pago CDP requiere cuentas de contrapartida y liquidez configuradas.'))
        return super().action_post()


class RegisterPayment(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('payment_type', 'company_id', 'can_edit_wizard', 'line_ids')
    def _compute_available_journal_ids(self):
        super()._compute_available_journal_ids()
        for wizard in self:
            circuits = wizard.line_ids.move_id.journal_id.cdp_circuit_id
            if len(circuits) > 1 or (circuits and any(not line.cdp_circuit_id for line in wizard.line_ids)):
                wizard.available_journal_ids = False
            else:
                wizard.available_journal_ids = wizard.available_journal_ids.filtered(lambda j: j.cdp_circuit_id == circuits)

    def action_create_payments(self):
        self.line_ids.check_access('write')
        return super().action_create_payments()


class PartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.constrains('debit_move_id', 'credit_move_id')
    def _check_cdp_reconciliation(self):
        for rec in self:
            if rec.debit_move_id.cdp_circuit_id != rec.credit_move_id.cdp_circuit_id:
                raise ValidationError(_('La conciliación no puede cruzar circuitos.'))


class Report(models.Model):
    _inherit = 'account.report'

    def _init_options_custom(self, options, previous_options):
        super()._init_options_custom(options, previous_options)
        scope = self.env.context.get('cdp_report_scope') or (previous_options or {}).get('cdp_scope', 'fiscal')
        options['cdp_scope'] = scope if self.env.user.has_group(GROUP) and scope in ('cdp', 'both') else 'fiscal'

    def _get_options_domain(self, options, date_scope):
        domain = super()._get_options_domain(options, date_scope)
        scope = options.get('cdp_scope', 'fiscal') if self.env.user.has_group(GROUP) else 'fiscal'
        if scope == 'both':
            return domain & (Domain('cdp_user_id', '=', False) | Domain('cdp_user_id', '=', self.env.uid))
        if scope == 'cdp':
            return domain & Domain('cdp_user_id', '=', self.env.uid)
        return domain & Domain('cdp_circuit_id', '=', False)


class Send(models.AbstractModel):
    _inherit = 'account.move.send'

    def _generate_and_send_invoices(self, moves, *args, **kwargs):
        if moves.cdp_circuit_id:
            raise AccessError(_('CDP está reservado para simulaciones internas.'))
        return super()._generate_and_send_invoices(moves, *args, **kwargs)
