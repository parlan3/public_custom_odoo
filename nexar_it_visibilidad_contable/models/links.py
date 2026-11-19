"""Classify polymorphic links at query time, including after a rule-cache hit."""
from odoo import api, fields, models, _
from odoo.fields import Domain
from odoo.exceptions import AccessError, ValidationError
from .access import OPERATOR

PROTECTED_MODELS = (
    'account.account', 'account.journal', 'account.move', 'account.move.line',
    'account.payment', 'account.payment.method.line', 'account.bank.statement',
    'account.bank.statement.line', 'account.partial.reconcile',
    'account.full.reconcile', 'account.analytic.line',
)


class LinkRestriction(models.AbstractModel):
    _name = 'nexar.accounting.link.restriction'
    _description = 'Acceso a datos relacionados con el circuito'

    restricted_accounting = fields.Boolean(
        string='Circuito con acceso restringido', compute='_compute_link_restriction',
        search='_search_link_restriction')

    def _link_model_field(self):
        return 'model' if self._name == 'mail.message' else 'res_model'

    @api.depends('res_id')
    def _compute_link_restriction(self):
        model_field = self._link_model_field()
        for record in self:
            model, res_id = record[model_field], record.res_id
            parent = self.env[model].sudo().browse(res_id).exists() if model in PROTECTED_MODELS and res_id else False
            record.restricted_accounting = bool(parent and parent.restricted_accounting)

    @api.model
    def _search_link_restriction(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise NotImplementedError('Operador de restricción no admitido')
        # Odoo may normalize boolean searches to in/not in.
        values = value if isinstance(value, (list, tuple)) else [value]
        want_true = True in values
        want_false = False in values
        if want_true and want_false:
            return Domain.TRUE if operator in ('=', 'in') else Domain.FALSE
        positive = want_true
        if operator in ('!=', 'not in'):
            positive = not positive
        domains = []
        for model in PROTECTED_MODELS:
            ids = self.env[model].sudo().search([('restricted_accounting', '=', True)]).ids
            if ids:
                domains.append(Domain(self._link_model_field(), '=', model) & Domain('res_id', 'in', ids))
        restricted = Domain.OR(domains)
        return restricted if positive else ~restricted

    @api.model_create_multi
    def create(self, vals_list):
        if any('restricted_accounting' in vals for vals in vals_list):
            raise AccessError(_('La restricción se obtiene del registro relacionado.'))
        records = super().create(vals_list)
        records._check_link_operation()
        records._check_link_sharing()
        return records

    def write(self, vals):
        self._check_link_operation()
        if 'restricted_accounting' in vals:
            raise AccessError(_('La restricción se obtiene del registro relacionado.'))
        result = super().write(vals)
        self.invalidate_recordset(['restricted_accounting'])
        self._check_link_operation()
        self._check_link_sharing()
        return result

    def _check_link_operation(self):
        self.invalidate_recordset(['restricted_accounting'])
        if not self.env.su and not self.env.user.has_group(OPERATOR) and any(self.mapped('restricted_accounting')):
            raise AccessError(_('No tenés permiso para modificar datos del circuito restringido.'))

    def _check_link_sharing(self):
        if self._name == 'ir.attachment':
            if any(record.restricted_accounting and (record.public or record.access_token) for record in self):
                raise ValidationError(_('No se pueden publicar adjuntos del circuito restringido ni generar enlaces de acceso.'))


class Attachment(models.Model):
    _name = 'ir.attachment'
    _inherit = ['ir.attachment', 'nexar.accounting.link.restriction']


class Message(models.Model):
    _name = 'mail.message'
    _inherit = ['mail.message', 'nexar.accounting.link.restriction']


class Activity(models.Model):
    _name = 'mail.activity'
    _inherit = ['mail.activity', 'nexar.accounting.link.restriction']


class Follower(models.Model):
    _name = 'mail.followers'
    _inherit = ['mail.followers', 'nexar.accounting.link.restriction']


class Thread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        # Followers and email recipients are not an authorization mechanism.
        # Keep notes inside the secured document, without outbound copies.
        if self._name in PROTECTED_MODELS and any(self.sudo().mapped('restricted_accounting')):
            return []
        return super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
