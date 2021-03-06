# Copyright 2019 Omar Castiñeira, Comunitea Servicios Tecnológicos S.L.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, fields


class AccountInvoiceReport(models.Model):

    _inherit = 'account.invoice.report'

    payment_mode_id = fields.Many2one('account.payment.mode', 'Payment mode')
    number = fields.Char('Number')
    benefit = fields.Float('Benefit')
    brand_name = fields.Char('Brand name')
    area_id = fields.Many2one('res.partner.area', 'Area')
    commercial_region_ids = fields.\
        Many2many(related='area_id.commercial_region_ids')
    contact_id = fields.Many2one('res.partner', 'Partner Contact',
                                 readonly=True)

    def _select(self):
        select_str = super()._select()
        select_str += ', sub.payment_mode_id as payment_mode_id,' \
                      ' sub.number as number' \
                      ", CASE WHEN sub.type IN ('out_refund') " \
                      "THEN -sub.benefit " \
                      " WHEN sub.type IN ('out_invoice') THEN sub.benefit " \
                      " ELSE 0 END as benefit" \
                      ', sub.name as brand_name, sub.area_id' \
                      ', sub.contact_id as contact_id'
        return select_str

    def _sub_select(self):
        select_str = super()._sub_select()
        select_str += ', ai.payment_mode_id,' \
                      ' ai.number , sum(ail.quantity * ail.price_unit * ' \
                      '(100.0-ail.discount) / 100.0) - ' \
                      'sum(coalesce(ail.cost_unit, 0)*ail.quantity) ' \
                      'as benefit, pb.name, rpa.id as area_id, ' \
                      'ai.partner_shipping_id as contact_id'
        return select_str

    def _from(self):
        from_str = super()._from()
        from_str += ' LEFT JOIN product_brand pb ON pt.product_brand_id = ' \
                    'pb.id LEFT JOIN res_partner_area rpa ON rpa.id = ' \
                    'partner.area_id LEFT JOIN res_partner rpc on rpc.id = ' \
                    'ai.partner_shipping_id'
        return from_str

    def _group_by(self):
        group_by_str = super()._group_by()
        group_by_str += ', ai.payment_mode_id,' \
                        ' ai.number,' \
                        ' pb.name, ' \
                        ' rpa.id, ai.partner_shipping_id'

        return group_by_str
