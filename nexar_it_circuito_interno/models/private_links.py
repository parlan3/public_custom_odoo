from odoo import api, fields, models, _
from odoo.exceptions import AccessError

PROTECTED_MODELS = ('account.move', 'account.payment', 'account.journal', 'account.account')


class PrivateLink(models.AbstractModel):
    _name = 'nexar.internal.private.link'
    _description = 'Titular de documentos internos vinculados'

    ni_user_id = fields.Many2one('res.users', readonly=True, copy=False, index=True)

    def _ni_link_owner(self, model, res_id):
        if model not in PROTECTED_MODELS or not res_id:
            return False
        record = self.env[model].sudo().browse(res_id).exists()
        return record.ni_user_id.id if record else False

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            if 'ni_user_id' in vals and not self.env.su:
                raise AccessError(_('El titular del vÃ­nculo se determina automÃ¡ticamente.'))
            model_field = 'model' if self._name == 'mail.message' else 'res_model'
            model = vals.get(model_field) or self.env.context.get('default_' + model_field)
            if self._name == 'mail.activity' and vals.get('res_model_id'):
                model = self.env['ir.model'].sudo().browse(vals['res_model_id']).model
            res_id = vals.get('res_id') or self.env.context.get('default_res_id')
            prepared.append(dict(vals, ni_user_id=self._ni_link_owner(model, res_id)))
        return super().create(prepared)

    def write(self, vals):
        if 'ni_user_id' in vals and not self.env.su:
            raise AccessError(_('El titular del vÃ­nculo se determina automÃ¡ticamente.'))
        model_field = 'model' if self._name == 'mail.message' else 'res_model'
        if self._name == 'mail.activity' and 'res_model_id' in vals:
            target_model = self.env['ir.model'].sudo().browse(vals['res_model_id']).model
            if any(record.res_model != target_model for record in self):
                raise AccessError(_('No se puede cambiar el modelo de una actividad.'))
        if model_field in vals or 'res_id' in vals:
            for record in self:
                owner = self._ni_link_owner(vals.get(model_field, record[model_field]),
                                            vals.get('res_id', record.res_id))
                if owner != record.ni_user_id.id:
                    raise AccessError(_('No se pueden trasladar vÃ­nculos entre circuitos.'))
        return super().write(vals)


class PrivateAttachment(models.Model):
    _name = 'ir.attachment'
    _inherit = ['ir.attachment', 'nexar.internal.private.link']


class PrivateMessage(models.Model):
    _name = 'mail.message'
    _inherit = ['mail.message', 'nexar.internal.private.link']


class PrivateActivity(models.Model):
    _name = 'mail.activity'
    _inherit = ['mail.activity', 'nexar.internal.private.link']


class PrivateFollower(models.Model):
    _name = 'mail.followers'
    _inherit = ['mail.followers', 'nexar.internal.private.link']
