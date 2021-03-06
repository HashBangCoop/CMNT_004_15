# © 2019 Comunitea
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from odoo import models, fields, tools


class StockPickingReport(models.Model):
    _name = 'stock.picking.report'
    _description = "Sales Picking Statistics"
    _auto = False
    _rec_name = 'date'

    _order = 'date desc'

    name = fields.Char('Picking Name', readonly=True)
    date = fields.Datetime('Date Order', readonly=True)
    date_done = fields.Datetime(readonly=True)
    product_id = fields.Many2one(
        'product.product', 'Product', readonly=True)
    product_uom_qty = fields.Float('# of Qty', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    commercial = fields.Many2one('res.users', 'Commercial', readonly=True)
    price_total = fields.Float('Total Price', readonly=True)
    categ_id = fields.Many2one(
        'product.category', 'Category of Product', readonly=True)
    nbr = fields.Integer('# of Lines', readonly=True)
    state = fields.Selection([
        ('draft', 'New'), ('cancel', 'Cancelled'),
        ('waiting', 'Waiting Another Move'),
        ('confirmed', 'Waiting Availability'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'),
        ('done', 'Done')], 'Picking Status', readonly=True)
    area_id = fields.Many2one('res.partner.area', 'Area', readonly=True)
    state_name = fields.Many2one('res.country.state', readonly=True)
    team_id = fields.Many2one('crm.team', 'Sales Team', readonly=True)
    product_state = fields.Selection([
        ('draft', 'In Development'),
        ('sellable', 'Normal'),
        ('end', 'End of Lifecycle'),
        ('obsolete', 'Obsolete'),
        ('make_to_order', 'Make to order')], 'Product State', readonly=True)

    def _select(self):
        select_str = """
             SELECT min(sm.id) as id,
                    sm.product_id as product_id,
                    t.uom_id as product_uom,
                    -- sum(l.product_uom_qty / u.factor * u2.factor)
                    sm.product_qty as product_uom_qty,
                    CASE WHEN p_pack.is_pack and SUM(sm_pack.price_unit) != 0 and count(pack_line.id) > 1 /*Kit con varios productos*/
                            THEN abs((SUM(pack_line_2.product_qty) * sm.price_unit) / SUM(pack_line.product_qty * sm_pack.price_unit)) *
                            (SUM(sol.price_unit * (1 - sol.discount/100)) / count(pack_line.id)) * SUM((sm.product_qty / pack_line_2.product_qty))
                          WHEN p_pack.is_pack and count(pack_line.id) = 1 
                            THEN (SUM(sol.price_unit * (1 - sol.discount/100)) / SUM(pack_line.product_qty))* SUM(sm.product_qty)
                          ELSE SUM(sol.price_unit * (1 - sol.discount/100)) * SUM(sm.product_qty) 
                    END as price_total,
                    count(*) as nbr,
                    s.date as date,
                    s.date_done as date_done,
                    rp.id as partner_id,
                    s.name as name,
                    s.commercial as commercial,
                    sm.state,
                    t.categ_id as categ_id,
                    rp.area_id as area_id,
                    rp.state_id as state_name,
                    rp.team_id as team_id, 
                    t.state as product_state
        """
        return select_str

    def _from(self):
        from_str = """
            stock_picking s
                    left join stock_move sm on sm.picking_id = s.id
                    left join res_partner r on (r.id = s.partner_id)
                    left join res_partner rp on
                        (rp.id = r.commercial_partner_id)
                    left join product_product p on (sm.product_id = p.id)
                        left join product_template t on
                            (p.product_tmpl_id = t.id)
                    left join stock_picking_type as pt on
                        (pt.id = s.picking_type_id)
                left join stock_location sl on (sl.id = sm.location_dest_id)
                left join product_uom u on (u.id = sm.product_uom)
                LEFT JOIN sale_order_line sol ON sol.id = sm.sale_line_id
                LEFT JOIN product_product p_pack ON p_pack.id = sol.product_id and COALESCE(p_pack.is_pack, False) = True  /*Ref pack si proviene de pack*/
                LEFT JOIN mrp_bom pack ON pack.product_id = p_pack.id AND pack.type = 'phantom'
                LEFT JOIN mrp_bom_line pack_line ON pack_line.bom_id = pack.id 
                LEFT JOIN mrp_bom_line pack_line_2 ON pack_line_2.bom_id = pack.id and pack_line_2.product_id = sm.product_id and pack_line_2.id = pack_line.id
                LEFT JOIN stock_move sm_pack ON sm_pack.sale_line_id = sm.sale_line_id 
                    and sm_pack.picking_type_id = sm.picking_type_id /*Para que no salgan devoluciones*/
                    and sm_pack.product_id = pack_line.product_id /*Asegurarnos que las lineas que encuentran son del pack*/
                    and sm_pack.state <> 'cancel'
                -- left join product_uom u2 on (u2.id = sm.uom_id)
        """

        return from_str

    def _where(self):
        where = """
            pt.code = 'outgoing' and sl.usage = 'customer' and  sm.product_qty != 0
        """
        return where

    def _group_by(self):
        group_by_str = """
            GROUP BY sm.id,
                    s.name,
                    t.uom_id,
                    t.categ_id,
                    s.date,
                    s.date_done,
                    r.parent_id,
                    s.commercial,
                    sm.state,
                    rp.id,
                    rp.area_id,
                    rp.state_id,
                    rp.team_id,
                    sm.id,
                    p_pack.id, 
                    t.state
        """
        return group_by_str

    def init(self):
        # self._table = sale_report
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute("""CREATE or REPLACE VIEW %s as (
            %s
            FROM ( %s )
            WHERE ( %s )
            %s
            )""" % (self._table, self._select(), self._from(),
                    self._where(), self._group_by()))
