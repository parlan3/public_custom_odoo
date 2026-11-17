from odoo import api, fields, models, Command, SUPERUSER_ID, _
from odoo.exceptions import AccessError, ValidationError

GROUP = 'nexar_it_circuito_interno.group_operator'
ACCOUNT_SPECS = [
    ('cash_ars', '1.1.1.01.901', 'Caja interna ARS', 'asset_cash', 'ARS', False),
    ('cash_usd', '1.1.1.01.902', 'Caja interna USD', 'asset_cash', 'USD', False),
    ('receivable', '1.1.3.01.901', 'Clientes internos', 'asset_receivable', False, True),
    ('payable', '2.1.1.01.901', 'Proveedores internos', 'liability_payable', False, True),
    ('income', '4.1.1.01.901', 'Ingresos por ventas internas', 'income', False, False),
    ('expense', '5.1.1.01.901', 'Gastos por compras internas', 'expense', False, False),
    ('transfer', '1.1.1.09.901', 'Transferencias internas del circuito', 'asset_current', False, True),
    ('surplus', '9.1.1.01.901', 'Sobrantes de caja interna', 'income_other', False, False),
    ('shortage', '5.1.1.01.902', 'Faltantes de caja interna', 'expense', False, False),
    ('fx_gain', '9.1.1.01.902', 'Ganancia de cambio interna', 'income_other', False, False),
    ('fx_loss', '5.1.1.01.903', 'Perdida de cambio interna', 'expense', False, False),
]
JOURNAL_SPECS = [
    ('INTV', 'Interno Ventas', 'sale', 'income', False),
    ('INTC', 'Interno Compras', 'purchase', 'expense', False),
    ('INARS', 'Interno Caja ARS', 'cash', 'cash_ars', 'ARS'),
    ('INUSD', 'Interno Caja USD', 'cash', 'cash_usd', 'USD'),
    ('INTAJ', 'Interno Ajustes', 'general', False, False),
    ('INTFX', 'Interno Diferencias de cambio', 'general', False, False),
]


class Circuit(models.Model):
    _name = 'nexar.internal.circuit'
    _description = 'Circuito interno'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    account_ids = fields.One2many('account.account', 'ni_circuit_id', readonly=True)
    journal_ids = fields.One2many('account.journal', 'ni_circuit_id', readonly=True)
    _company_unique = models.Constraint('UNIQUE(company_id)', 'La compaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­a ya tiene un circuito.')

    def write(self, vals):
        if {'user_id', 'company_id'} & vals.keys():
            raise AccessError(_('El titular y la compaÃ±Ã­a del circuito son fijos. Una transferencia requiere migraciÃ³n.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Los circuitos se conservan junto con sus registros contables.'))

    def _account(self, role):
        self.ensure_one()
        account = self.env['account.account'].search([
            ('ni_circuit_id', '=', self.id), ('ni_role', '=', role),
        ])
        if len(account) != 1:
            raise ValidationError(_('Falta una cuenta ÃƒÆ’Ã‚Âºnica del circuito para %s.', role))
        return account

    def _journal(self, code):
        self.ensure_one()
        return self.env['account.journal'].search([
            ('ni_circuit_id', '=', self.id), ('code', '=', code),
        ], limit=1)

    def _initialize(self):
        # Only invoked by the administrator wizard. No public sudo configuration method.
        self.ensure_one()
        if self.env.uid != SUPERUSER_ID:
            raise AccessError(_('La configuraciÃƒÆ’Ã‚Â³n requiere el asistente de administraciÃƒÆ’Ã‚Â³n.'))
        company = self.company_id
        accounts = self.env['account.account'].with_company(company)
        currencies = self.env['res.currency'].with_context(active_test=False)
        currency_map = {}
        for name in ('ARS', 'USD'):
            currency = currencies.search([('name', '=', name)], limit=1)
            if not currency:
                raise ValidationError(_('Falta la moneda %s.', name))
            if not currency.active:
                currency.active = True
            currency_map[name] = currency.id
        if company.currency_id.name != 'ARS':
            raise ValidationError(_('Esta configuraciÃƒÆ’Ã‚Â³n estÃƒÆ’Ã‚Â¡ preparada para compaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­as en ARS.'))
        for role, code, name, kind, currency, reconcile in ACCOUNT_SPECS:
            account = accounts.with_context(active_test=False).search([
                ('company_ids', 'in', company.ids), ('code', '=', code),
            ])
            if len(account) > 1:
                raise ValidationError(_('CÃƒÆ’Ã‚Â³digo duplicado %s.', code))
            values = dict(name=name, code=code, account_type=kind,
                          company_ids=[Command.set(company.ids)],
                          ni_circuit_id=self.id, ni_role=role,
                          currency_id=currency_map.get(currency, False), reconcile=reconcile)
            if account:
                if (account.company_ids != company or account.name != name
                        or account.account_type != kind or not account.active
                        or (account.ni_circuit_id and account.ni_circuit_id != self)
                        or ('cdp_circuit_id' in account._fields and account.cdp_circuit_id)):
                    raise ValidationError(_('La cuenta %s requiere revisiÃƒÆ’Ã‚Â³n antes de adoptarla.', code))
                if not account.ni_circuit_id and self.env['account.move.line'].search_count(
                        [('account_id', '=', account.id)], limit=1):
                    raise ValidationError(_('La cuenta %s ya tiene apuntes. Se requiere migraciÃƒÆ’Ã‚Â³n revisada.', code))
                account.write(values)
            else:
                accounts.create(values)
        journals = self.env['account.journal'].with_company(company)
        for code, name, kind, role, currency in JOURNAL_SPECS:
            journal = journals.with_context(active_test=False).search([
                ('company_id', '=', company.id), ('code', '=', code),
            ])
            if len(journal) > 1:
                raise ValidationError(_('Diario duplicado %s.', code))
            values = dict(name=name, code=code, type=kind, company_id=company.id,
                          ni_circuit_id=self.id, l10n_latam_use_documents=False,
                          l10n_ar_afip_pos_number=0, currency_id=currency_map.get(currency, False))
            if role:
                values['default_account_id'] = self._account(role).id
            if kind == 'cash':
                values.update(suspense_account_id=self._account('transfer').id,
                              profit_account_id=self._account('surplus').id,
                              loss_account_id=self._account('shortage').id)
            if journal:
                if (journal.name != name or journal.type != kind or not journal.active
                        or (journal.ni_circuit_id and journal.ni_circuit_id != self)
                        or ('cdp_circuit_id' in journal._fields and journal.cdp_circuit_id)):
                    raise ValidationError(_('El diario %s requiere revisiÃƒÆ’Ã‚Â³n antes de adoptarlo.', code))
                if not journal.ni_circuit_id and self.env['account.move'].search_count(
                        [('journal_id', '=', journal.id)], limit=1):
                    raise ValidationError(_('El diario %s ya tiene movimientos. Requiere migraciÃƒÆ’Ã‚Â³n revisada.', code))
                journal.write(values)
            else:
                journal = journals.create(values)
            if kind == 'cash':
                methods = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
                if any(line.code != 'manual' for line in methods):
                    raise ValidationError(_('La caja interna requiere mÃƒÆ’Ã‚Â©todos manuales exclusivamente.'))
                methods.write({'payment_account_id': journal.default_account_id.id})


class Setup(models.TransientModel):
    _name = 'nexar.internal.setup'
    _description = 'Configurar circuito interno'

    company_ids = fields.Many2many('res.company', required=True, string='CompaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­as')
    user_id = fields.Many2one('res.users', required=True, string='Usuario titular',
                             domain=[('share', '=', False), ('active', '=', True)])
    acknowledge = fields.Boolean(string='Confirmo asignar el usuario exclusivamente al circuito interno')
    migrate_legacy = fields.Boolean(string='Reemplazar las reglas manuales de esta implementaciÃƒÆ’Ã‚Â³n', default=True)

    def action_configure(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Se requieren permisos de Ajustes.'))
        if not self.acknowledge or not self.company_ids:
            raise ValidationError(_('SeleccionÃƒÆ’Ã‚Â¡ compaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­as y confirmÃƒÆ’Ã‚Â¡ los permisos del titular.'))
        if self.company_ids - self.env.user.company_ids:
            raise AccessError(_('SeleccionÃƒÆ’Ã‚Â¡ compaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­as permitidas para tu usuario.'))
        owner = self.user_id
        if (not owner.active or owner.share or owner == self.env.user or owner.id == SUPERUSER_ID
                or owner.has_group('base.group_system')):
            raise ValidationError(_('UsÃƒÂ¡ un usuario interno dedicado, sin administraciÃƒÂ³n.'))
        cdp_group = self.env.ref('nexar_it_contabilidad_pruebas.group_operator', raise_if_not_found=False)
        if cdp_group and owner.has_group('nexar_it_contabilidad_pruebas.group_operator'):
            raise ValidationError(_('El titular del circuito independiente debe ser distinto del titular CDP.'))
        # Lock the selected companies to serialize repeated setup submissions.
        self.env.cr.execute('SELECT id FROM res_company WHERE id IN %s ORDER BY id FOR UPDATE',
                            [tuple(self.company_ids.ids)])
        admin = self.env['nexar.internal.circuit'].with_user(SUPERUSER_ID)
        existing = admin.search([])
        if existing and (existing.user_id != owner or set(existing.company_id.ids) != set(self.company_ids.ids)):
            raise ValidationError(_('Ya hay otra selecciÃƒÆ’Ã‚Â³n de titular o compaÃƒÆ’Ã‚Â±ÃƒÆ’Ã‚Â­as. RevisÃƒÆ’Ã‚Â¡ la migraciÃƒÆ’Ã‚Â³n.'))
        for company in self.company_ids:
            circuit = existing.filtered(lambda c: c.company_id == company)
            if not circuit:
                circuit = admin.create(dict(name='Interno - ' + company.name,
                                            company_id=company.id, user_id=owner.id))
            circuit._initialize()
        circuits = admin.search([('company_id', 'in', self.company_ids.ids)])
        # Backfill existing chatter on adopted accounts/journals before enabling operation.
        for model, records in [('account.account', circuits.account_ids),
                               ('account.journal', circuits.journal_ids)]:
            for link_model in ('ir.attachment', 'mail.message', 'mail.activity', 'mail.followers'):
                field = 'model' if link_model == 'mail.message' else 'res_model'
                links = self.env[link_model].with_user(SUPERUSER_ID).search([
                    (field, '=', model), ('res_id', 'in', records.ids)])
                links.write({'ni_user_id': owner.id})
        if self.migrate_legacy:
            self._retire_legacy(circuits)
        owner.sudo().write({
            'company_ids': [Command.set(self.company_ids.ids)],
            'company_id': self.company_ids.sorted('id')[0].id,
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id, self.env.ref('base.group_multi_company').id,
                self.env.ref(GROUP).id,
            ])],
        })
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': 'Circuito interno', 'message': 'ConfiguraciÃƒÆ’Ã‚Â³n aplicada. EjecutÃƒÆ’Ã‚Â¡ las pruebas en staging.',
            'type': 'success', 'sticky': True,
        }}

    def _retire_legacy(self, circuits):
        # Only replace the eleven exact rules created for the previous manual setup.
        models_paths = {
            'account.account': 'id', 'account.journal': 'id', 'account.move': 'journal_id',
            'account.move.line': 'journal_id', 'account.payment': 'journal_id',
            'account.bank.statement': 'journal_id', 'account.bank.statement.line': 'journal_id',
            'account.invoice.report': 'journal_id', 'account.payment.method.line': 'journal_id',
            'account.partial.reconcile': 'debit_move_id.journal_id',
            'account.full.reconcile': 'reconciled_line_ids.journal_id',
        }
        journals = circuits.journal_ids.filtered(lambda j: j.code != 'INTFX')
        accounts = circuits.account_ids.filtered(lambda a: a.ni_role not in ('fx_gain', 'fx_loss'))
        for model, path in models_paths.items():
            rule = self.env['ir.rule'].sudo().search([
                ('name', '=', 'Circuito interno exclusivo / ' + model), ('active', '=', True),
            ])
            if not rule:
                continue
            ids = sorted((accounts if model == 'account.account' else journals).ids)
            paths = [path] + (['credit_move_id.journal_id'] if model == 'account.partial.reconcile' else [])
            expected = (f"{[(p, 'in', ids) for p in paths]!r} if user.id == {self.user_id.id} else "
                        f"{[(p, 'not in', ids) for p in paths]!r}")
            if len(rule) != 1 or rule.model_id.model != model or rule.domain_force != expected:
                raise ValidationError(_('La regla manual de %s difiere de la esperada. Revisala.', model))
            rule.active = False
