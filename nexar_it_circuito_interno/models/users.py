from odoo import api, fields, models, Command, _
from odoo.exceptions import AccessError


class Users(models.Model):
    _inherit = 'res.users'

    ni_menu_enabled = fields.Boolean(
        string='Mostrar Circuito interno',
        compute='_compute_ni_menu_enabled', inverse='_inverse_ni_menu_enabled',
        groups='base.group_system',
        help='Habilita el men\u00fa para este usuario. Los permisos operativos y de configuraci\u00f3n se verifican por separado.',
    )

    @api.depends('group_ids')
    def _compute_ni_menu_enabled(self):
        group = self.env.ref('nexar_it_circuito_interno.group_menu')
        for user in self:
            user.ni_menu_enabled = group in user.group_ids

    def _inverse_ni_menu_enabled(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Se requieren permisos de Ajustes para habilitar el men\u00fa.'))
        group = self.env.ref('nexar_it_circuito_interno.group_menu')
        for user in self:
            command = Command.link(group.id) if user.ni_menu_enabled else Command.unlink(group.id)
            user.write({'group_ids': [command]})
