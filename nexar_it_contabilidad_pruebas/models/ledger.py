import os

from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tools import float_compare


class Circuit(models.Model):
    _name = 'nexar.test.circuit'
    _description = 'Circuito contable de pruebas'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    currency_id = fields.Many2one(related='company_id.currency_id')
    _company_unique = models.Constraint('UNIQUE(company_id)', 'Ya existe un circuito para esta compañía.')

    def _initialize_target(self, companies, user):
        # Private method, called only by the administrator configuration wizard.
        operator = self.env.ref('nexar_it_contabilidad_pruebas.group_operator')
        readonly = self.env.ref('account.group_account_readonly')
        user.write({
            'company_ids': [Command.set(companies.ids)],
            'company_id': companies.sorted('id')[0].id,
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('base.group_multi_company').id, readonly.id, operator.id,
            ])],
        })
        for company in companies:
            circuit = self.sudo().search([('company_id', '=', company.id)], limit=1)
            if circuit:
                if circuit.user_id != user:
                    raise ValidationError(_('El circuito existente tiene otro titular.'))
                continue
            circuit = self.sudo().create({
                'name': 'PRUEBAS - ' + company.name,
                'company_id': company.id, 'user_id': user.id,
            })
            source = self.env['account.account'].sudo().with_company(company).search([
                ('company_ids', 'in', company.ids), ('active', '=', True),
            ])
            self.env['nexar.test.account'].sudo().create([
                {'circuit_id': circuit.id, 'code': a.code, 'name': a.name,
                 'account_type': a.account_type} for a in source
            ])
            for code, name, kind in [
                ('TV', 'Ventas de prueba', 'sale'),
                ('TC', 'Compras de prueba', 'purchase'),
                ('TB', 'Banco de prueba', 'bank'),
                ('TE', 'Caja de prueba', 'cash'),
                ('TG', 'Asientos de prueba', 'general'),
            ]:
                self.env['nexar.test.journal'].sudo().create({
                    'name': name, 'code': code, 'kind': kind,
                    'circuit_id': circuit.id,
                })


class Setup(models.TransientModel):
    _name = 'nexar.test.setup'
    _description = 'Configurar CDP'

    company_ids = fields.Many2many('res.company', string='Compañías', required=True)
    user_id = fields.Many2one('res.users', string='Usuario titular', required=True,
                             domain=[('share', '=', False), ('active', '=', True)])
    acknowledge = fields.Boolean(string='Confirmo reemplazar los grupos y compañías del usuario seleccionado')

    def action_configure(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('La configuración requiere permisos de Ajustes.'))
        self.check_access('read')
        if not self.company_ids or not self.acknowledge:
            raise ValidationError(_('Seleccioná las compañías y confirmá el cambio de permisos.'))
        if self.user_id == self.env.user or self.user_id.id == 1 or self.user_id.share or not self.user_id.active:
            raise ValidationError(_('Seleccioná otro usuario interno activo que no sea superusuario.'))
        if self.user_id.has_group('base.group_system'):
            raise ValidationError(_('El titular debe ser un usuario sin permisos de administración.'))
        stage = (os.environ.get('ODOO_STAGE') == 'staging'
                 or '-stage-' in self.env.cr.dbname
                 or self.env['ir.config_parameter'].sudo().get_param('database.is_neutralized') == 'True')
        if not stage:
            raise UserError(_('Este asistente requiere un entorno de pruebas neutralizado o staging.'))
        self.company_ids.check_access('read')
        if self.company_ids - self.env.user.company_ids:
            raise AccessError(_('Solo podés configurar compañías asignadas a tu usuario.'))
        circuits = self.env['nexar.test.circuit'].sudo()
        existing = circuits.search([])
        if existing and (existing.user_id != self.user_id or set(existing.company_id.ids) != set(self.company_ids.ids)):
            raise ValidationError(_('Ya existe una configuración diferente. Revisala antes de cambiar titular o compañías.'))
        circuits._initialize_target(self.company_ids, self.user_id)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': 'CDP', 'message': 'Circuitos configurados.', 'type': 'success',
            'next': {'type': 'ir.actions.act_window_close'},
        }}


class Account(models.Model):
    _name = 'nexar.test.account'
    _description = 'Cuenta de pruebas'
    _rec_name = 'name'
    _order = 'code, id'
    _check_company_auto = True

    circuit_id = fields.Many2one('nexar.test.circuit', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='circuit_id.company_id', store=True)
    user_id = fields.Many2one(related='circuit_id.user_id', store=True)
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    account_type = fields.Char(readonly=True)
    _code_unique = models.Constraint('UNIQUE(circuit_id, code)', 'El código ya existe en este circuito.')

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for account in self:
            account.display_name = f'{account.code} {account.name}'


class Journal(models.Model):
    _name = 'nexar.test.journal'
    _description = 'Diario de pruebas'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    kind = fields.Selection([('sale', 'Ventas'), ('purchase', 'Compras'),
                            ('bank', 'Banco'), ('cash', 'Caja'), ('general', 'General')], required=True)
    circuit_id = fields.Many2one('nexar.test.circuit', required=True, ondelete='restrict')
    company_id = fields.Many2one(related='circuit_id.company_id', store=True)
    user_id = fields.Many2one(related='circuit_id.user_id', store=True)
    _code_unique = models.Constraint('UNIQUE(circuit_id, code)', 'El diario ya existe en este circuito.')


class Move(models.Model):
    _name = 'nexar.test.move'
    _description = 'Movimiento de pruebas sin validez fiscal'
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(default='Borrador', required=True, readonly=True, copy=False)
    journal_id = fields.Many2one('nexar.test.journal', required=True, ondelete='restrict')
    circuit_id = fields.Many2one(related='journal_id.circuit_id', store=True)
    company_id = fields.Many2one(related='journal_id.company_id', store=True)
    user_id = fields.Many2one(related='journal_id.user_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(required=True, default=fields.Date.context_today)
    ref = fields.Char(string='Referencia de prueba')
    state = fields.Selection([('draft', 'Borrador'), ('posted', 'Confirmado')], default='draft', required=True, readonly=True, copy=False)
    line_ids = fields.One2many('nexar.test.line', 'move_id', copy=True)
    debit = fields.Monetary(compute='_compute_totals', store=True)
    credit = fields.Monetary(compute='_compute_totals', store=True)
    note = fields.Text()

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_totals(self):
        for move in self:
            move.debit = sum(move.line_ids.mapped('debit'))
            move.credit = sum(move.line_ids.mapped('credit'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft' or vals.get('name', 'Borrador') != 'Borrador':
                raise ValidationError(_('Los movimientos se crean como borradores.'))
            self.env['nexar.test.journal'].browse(vals['journal_id']).check_access('read')
        return super().create(vals_list)

    def _lock(self):
        self.check_access('write')
        # Serialize posting, editing and line changes on the same move.
        if self.ids:
            self.env.cr.execute('SELECT id FROM nexar_test_move WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset(['state', 'line_ids', 'debit', 'credit'])

    def write(self, vals):
        self._lock()
        if 'state' in vals or 'name' in vals:
            raise AccessError(_('Usá los botones de confirmar o volver a borrador.'))
        if any(m.state != 'draft' for m in self):
            raise UserError(_('Volvé a borrador antes de modificar el movimiento.'))
        if 'journal_id' in vals:
            journal = self.env['nexar.test.journal'].browse(vals['journal_id'])
            journal.check_access('read')
            if any(m.circuit_id != journal.circuit_id for m in self):
                raise ValidationError(_('No se puede trasladar un movimiento a otro circuito.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Los movimientos se conservan para revisión. Podés modificar los borradores.'))

    def action_post(self):
        self._lock()
        for move in self:
            if move.state == 'posted':
                continue
            precision = move.currency_id.rounding
            if len(move.line_ids) < 2 or float_compare(move.debit, 0, precision_rounding=precision) <= 0:
                raise ValidationError(_('Ingresá al menos dos líneas y un importe positivo.'))
            if float_compare(move.debit, move.credit, precision_rounding=precision):
                raise ValidationError(_('El debe y el haber deben ser iguales.'))
            name = move.name
            if name == 'Borrador':
                name = f'PRUEBA/{move.journal_id.code}/{move.id:06d}'
            super(Move, move).write({'state': 'posted', 'name': name})
        return True

    def action_draft(self):
        self._lock()
        return super().write({'state': 'draft'})


class Line(models.Model):
    _name = 'nexar.test.line'
    _description = 'Apunte de pruebas'
    _order = 'date, move_id, id'
    _check_company_auto = True

    move_id = fields.Many2one('nexar.test.move', required=True, ondelete='cascade')
    circuit_id = fields.Many2one(related='move_id.circuit_id', store=True)
    company_id = fields.Many2one(related='move_id.company_id', store=True)
    user_id = fields.Many2one(related='move_id.user_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(related='move_id.date', store=True)
    state = fields.Selection(related='move_id.state', store=True)
    account_id = fields.Many2one('nexar.test.account', required=True, ondelete='restrict', check_company=True)
    label = fields.Char(string='Concepto', required=True)
    counterparty = fields.Char(string='Tercero de prueba')
    debit = fields.Monetary(default=0)
    credit = fields.Monetary(default=0)
    balance = fields.Monetary(compute='_compute_balance', store=True)
    _amounts = models.Constraint('CHECK(debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0))', 'Cada línea debe tener un importe no negativo en debe o haber.')

    @api.depends('debit', 'credit')
    def _compute_balance(self):
        for line in self:
            line.balance = line.debit - line.credit

    @api.constrains('account_id', 'move_id')
    def _check_circuit(self):
        for line in self:
            line.account_id.check_access('read')
            if line.account_id.circuit_id != line.circuit_id:
                raise ValidationError(_('La cuenta debe pertenecer al circuito del movimiento.'))

    def _check_draft(self, moves):
        moves._lock()
        if any(m.state != 'draft' for m in moves):
            raise UserError(_('Solo se pueden modificar líneas de borradores.'))

    @api.model_create_multi
    def create(self, vals_list):
        moves = self.env['nexar.test.move'].browse([v['move_id'] for v in vals_list])
        self._check_draft(moves)
        return super().create(vals_list)

    def write(self, vals):
        if 'move_id' in vals:
            raise AccessError(_('No se pueden trasladar líneas entre movimientos.'))
        self._check_draft(self.move_id)
        return super().write(vals)

    def unlink(self):
        self._check_draft(self.move_id)
        return super().unlink()
