# Copyright 2019 Omar Castiñeira, Comunitea Servicios Tecnológicos S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import api, models
import base64


class SaleOrder(models.Model):

    _inherit = "sale.order"

    @api.multi
    def attach_ubl_xml_file_button(self):
        self.ensure_one()
        version = self.get_ubl_version()
        doc_type = 'quotation'
        xml_string = self.generate_ubl_xml_string(doc_type, version=version)
        filename = self.get_ubl_filename(doc_type, version=version)
        ctx = {}
        attach = self.env['ir.attachment'].with_context(ctx).create({
            'name': filename,
            'res_id': self.id,
            'res_model': str(self._name),
            'datas': base64.b64encode(xml_string),
            'datas_fname': filename,
            # I have default_type = 'out_invoice' in context, so 'type'
            # would take 'out_invoice' value by default !
            'type': 'binary',
            })
        action = self.env['ir.actions.act_window'].for_xml_id(
            'base', 'action_attachment')
        action.update({
            'res_id': attach.id,
            'views': False,
            'view_mode': 'form,tree'
            })
        return action
