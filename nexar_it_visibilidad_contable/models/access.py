from odoo import api, fields, models, _, Command, SUPERUSER_ID
from odoo.exceptions import AccessError, ValidationError

ACCESS = 'nexar_it_visibilidad_contable.group_access'
OPERATOR = 'nexar_it_visibilidad_contable.group_operator'
READER = 'nexar_it_visibilidad_contable.group_reader'


def can_access(env):
    return env.uid == SUPERUSER_ID or env.user.has_group(ACCESS)


def check_marker(env, values):
    if 'restricted_accounting' in values and not env.su and not env.user.has_group('base.group_system'):
        raise AccessError(_('Solo un administrador de Ajustes puede clasificar diarios y cuentas.'))


def validate_classification(env):
    # Check all dependent attachment models, not only the journal/account.
    if env['ir.attachment'].sudo().search_count([
        ('restricted_accounting', '=', True), '|', ('public', '=', True), ('access_token', '!=', False)
    ], limit=1):
        raise ValidationError(_('Existen adjuntos con enlaces públicos en el circuito. Revocá esos enlaces antes de restringirlo.'))


class Users(models.Model):
    _inherit = 'res.users'

    restricted_accounting_access = fields.Selection([
        ('none', 'Sin acceso'), ('read', 'Solo consulta'), ('operate', 'Operación')],
        string='Acceso al circuito contable restringido',
        compute='_compute_restricted_accounting_access', inverse='_inverse_restricted_accounting_access',
        groups='base.group_system',
        help='Visibilidad adicional del circuito. Las empresas autorizadas y los permisos contables nativos siguen aplicándose.')

    @api.depends('group_ids')
    def _compute_restricted_accounting_access(self):
        operator = self.env.ref(OPERATOR)
        access = self.env.ref(ACCESS)
        for user in self:
            user.restricted_accounting_access = ('operate' if operator in user.group_ids
                                                  else 'read' if access in user.group_ids else 'none')

    def _inverse_restricted_accounting_access(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Se requieren permisos de Ajustes para habilitar el circuito.'))
        op, read, access = [self.env.ref(x) for x in [OPERATOR, READER, ACCESS]]
        for user in self:
            value = user.restricted_accounting_access
            commands = [Command.unlink(g.id) for g in (op, read, access)]
            if value != 'none':commands.append(Command.link((op if value=='operate' else read).id))
            user.write({'group_ids': commands})

    @api.constrains('group_ids')
    def _check_restricted_profiles(self):
        op = self.env.ref(OPERATOR, raise_if_not_found=False)
        read = self.env.ref(READER, raise_if_not_found=False)
        if op and read:
            for user in self:
                if op in user.group_ids and read in user.group_ids:
                    raise ValidationError(_('Elegí un solo nivel de acceso al circuito: consulta u operación.'))


class Account(models.Model):
    _inherit = 'account.account'
    restricted_accounting = fields.Boolean(string='Circuito con acceso restringido', default=False,
        index=True, copy=False, help='Solo los usuarios habilitados podrán consultar esta cuenta y sus movimientos.')

    @api.model
    def _get_most_frequent_accounts_for_partner(self, company_id, partner_id, move_type, filter_never_user_accounts=False, limit=None):
        # Native suggestions use bypass_access and name_search renders them
        # with sudo. Filter these IDs before they leave the server.
        ids = super()._get_most_frequent_accounts_for_partner(
            company_id, partner_id, move_type, filter_never_user_accounts, limit=None)
        if not can_access(self.env):
            allowed = set(self.sudo().search([('id', 'in', ids), ('restricted_accounting', '=', False)]).ids)
            ids = [record_id for record_id in ids if record_id in allowed]
        return ids[:limit] if limit else ids

    @api.model
    def _get_most_frequent_account_for_partner(self, company_id, partner_id, move_type=None):
        account_id = super()._get_most_frequent_account_for_partner(company_id, partner_id, move_type)
        # The native transaction cache does not include uid in its key.
        if account_id and not can_access(self.env) and self.sudo().browse(account_id).restricted_accounting:
            return False
        return account_id

    @api.model
    @api.readonly
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        results = super().name_search(name=name, domain=domain, operator=operator, limit=limit)
        if not can_access(self.env):
            allowed = set(self.sudo().search([('id', 'in', [row[0] for row in results]), ('restricted_accounting', '=', False)]).ids)
            results = [row for row in results if row[0] in allowed]
        return results

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:check_marker(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        check_marker(self.env, vals)
        result = super().write(vals)
        if vals.get('restricted_accounting'):
            from .records import validate_shared_attachments
            validate_shared_attachments(self.env, self._name, self.ids)
            self.env['account.move.line'].sudo().search([('account_id','in',self.ids)]).move_id._check_no_public_restricted_access()
            self.env['account.payment'].sudo().search([('destination_account_id','in',self.ids)])._check_no_public_restricted_access()
            validate_classification(self.env)
        return result


class Journal(models.Model):
    _inherit = 'account.journal'
    restricted_accounting = fields.Boolean(string='Circuito con acceso restringido', default=False,
        index=True, copy=False, help='Restringe el diario y todos sus movimientos a los usuarios habilitados.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:check_marker(self.env, vals)
        return super().create(vals_list)

    def write(self, vals):
        check_marker(self.env, vals)
        result = super().write(vals)
        if vals.get('restricted_accounting'):
            from .records import validate_shared_attachments
            validate_shared_attachments(self.env, self._name, self.ids)
            self.env['account.move'].sudo().search([('journal_id','in',self.ids)])._check_no_public_restricted_access()
            self.env['account.payment'].sudo().search([('journal_id','in',self.ids)])._check_no_public_restricted_access()
            validate_classification(self.env)
        return result
