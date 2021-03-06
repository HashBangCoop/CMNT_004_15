# Copyright 2019 Omar Castiñeira, Comunitea Servicios Tecnológicos S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, exceptions, _


class PurchaseOrderLine(models.Model):

    _inherit = "purchase.order.line"

    @api.multi
    def _prepare_stock_moves(self, picking):
        res = super()._prepare_stock_moves(picking)
        if self.order_id.picking_type_id.force_location:
            for move_dict in res:
                move_dict['location_id'] = \
                    self.order_id.picking_type_id.default_location_src_id.id
        return res


class ProrementRule(models.Model):

    _inherit = "procurement.rule"

    def _prepare_purchase_order(self, product_id, product_qty, product_uom,
                                origin, values, partner):
        res = super()._prepare_purchase_order(product_id, product_qty,
                                              product_uom, origin, values,
                                              partner)
        if partner.automatice_purchases:
            res['force_confirm'] = True
            res['date_planned'] = fields.Datetime.now()
        return res


class PurchaseOrder(models.Model):

    _inherit = "purchase.order"

    force_confirm = fields.Boolean()

    @api.model
    def _process_purchase_order_automated(self):
        purchases = self.search([('force_confirm', '=', True),
                                 ('order_line', '!=', False),
                                 ('state', '=', 'draft')])
        for order in purchases:
            order.with_context(bypass_override=True).button_confirm()
            action = order.attach_ubl_xml_file_button()
            attachment = self.env['ir.attachment'].browse(action['res_id'])
            output_folder = self.env['base.io.folder'].\
                search([('direction', '=', 'export')], limit=1)
            if not output_folder:
                raise exceptions.UserError(_("Please create an export folder"))
            output_folder.export_file(attachment.datas, attachment.name)
            for pick in order.picking_ids:
                pick.not_sync = True
                pick.action_assign()
                pick.action_done()
