# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 Pexego All Rights Reserved
#    $Jesús Ventosinos Mayor <jesus@pexego.es>$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import models, fields, api
import ipdb

class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    @api.one
    def get_mandate_scheme(self):
        if self.invoice and self.invoice.mandate_id:
            self.scheme = self.invoice.mandate_id.scheme

    @api.model
    def _mandate_scheme_search(self, operator, operand):
        invoice_obj = self.env['account.invoice']
        invoices = invoice_obj.search([('mandate_id.scheme', operator,
                                        operand), ('move_id', '!=', False)])
        moves = [x.move_id.id for x in invoices]
        return [('move_id', 'in', moves)]

    scheme = fields.Selection(selection=[('CORE', 'Basic (CORE)'),
                                         ('B2B', 'Enterprise (B2B)')],
                              string='Scheme',
                              compute='get_mandate_scheme',
                              search='_mandate_scheme_search')
    partner_vat = fields.Char("CIF/NIF/VAT", related="partner_id.vat",
                              readonly=True)


class AccountBankingMandate(models.Model):

    _inherit = 'account.banking.mandate'

    default = fields.Boolean('Set default')


class AccountInvoiceLine(models.Model):

    _inherit = 'account.invoice.line'

    move_id = fields.Many2one('stock.move', 'Move', copy=False)
    picking_id = fields.Many2one("stock.picking", "Picking",
                                 related="move_id.picking_id",
                                 readonly=True)
    purchase_supplier_reference = fields.Char(
        'Supplier reference', related='purchase_line_id.order_id.partner_ref',
        readonly=True)
    active = fields.Boolean(default=True)
    sale_order_line_ids = fields.\
        Many2many('sale.order.line', 'sale_order_line_invoice_rel',
                  'invoice_id', 'order_line_id', 'Sale Lines', readonly=True,
                  copy=False)
    sale_order_id = fields.Many2one("sale.order", "Sale", readonly=True,
                                    related="sale_order_line_ids.order_id")


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    attach_picking = fields.Boolean('Attach picking')
    picking_ids = fields.One2many('stock.picking', string='pickings',
                                  compute='_get_picking_ids')
    sale_order_ids = fields.Many2many('sale.order', 'sale_order_invoice_rel',
                                      'invoice_id', 'order_id', 'Sale Orders',
                                      readonly=True, copy=False,
                                      help="This is the list of sale orders "
                                           "linked to this invoice. ")
    country_id = fields.Many2one('res.country', 'Country',
                                 related="partner_id.country_id",
                                 readonly=True, store=False)
    invoice_type_id = fields. \
        Many2one('res.partner.invoice.type', 'Invoice type', readonly=True,
                 related="invoice_line.picking_id.invoice_type_id")
    active = fields.Boolean(default=True)
    not_send_email = fields.Boolean("Not send email")
    total = fields.Float("Total Paid", compute="total_paid")
    last_payment = fields.Date("Last Payment", compute="last_payment_date")
    partner_commercial = fields.Char("Commercial", compute="get_comercial")
    subtotal_wt_rect = fields.Float("Real Subtotal", compute="get_subtotal_wt_rect", store=True)

    @api.multi
    def get_subtotal_wt_rect(self):
        for invoice in self:
            invoice_wt_rect = 0
            if "R" in invoice.number:
                invoice_wt_rect -= invoice.amount_untaxed
            else:
                invoice_wt_rect += invoice.amount_untaxed

            invoice.subtotal_wt_rect = invoice_wt_rect

    @api.one
    @api.depends('invoice.amount_untaxed')
    def _get_subtotal_wt_rect(self):
        self.subtotal_wt_rect = 10

    @api.multi
    def get_comercial(self):
        for invoice in self:
            invoice.partner_commercial = invoice.partner_id.user_id.name

    @api.multi
    def total_paid(self):
        for invoice in self:
            invoice_paid = 0
            for payment in invoice.payment_ids:
                if "R" in invoice.number:
                    invoice_paid += payment.debit
                else:
                    invoice_paid += payment.credit

            invoice.total = invoice_paid

    @api.multi
    def last_payment_date(self):
        for invoice in self:
            if invoice.payment_ids:
                len_payment = len(invoice.payment_ids) - 1
                invoice.last_payment = invoice.payment_ids[len_payment].last_rec_date

    @api.model
    def create(self, vals):
        if vals.get('partner_id', False):
            partner = self.env["res.partner"].browse(vals["partner_id"])
            if partner.attach_picking:
                vals["attach_picking"] = partner.attach_picking
        if 'type' in vals and 'partner_bank_id' in vals:
            if vals['type'] == 'out_invoice':
                partner_bank = self.env['res.partner.bank']. \
                    browse(vals['partner_bank_id'])
                mandate_ids = partner_bank.mandate_ids
                default_mandate = mandate_ids.filtered(
                    lambda r: r.default and r.state == "valid")
                if not default_mandate:
                    default_mandate = mandate_ids.filtered(
                        lambda r: r.state == "valid")
                vals['mandate_id'] = default_mandate and \
                                     default_mandate[0].id or False
        return super(AccountInvoice, self).create(vals)

    @api.multi
    def onchange_partner_bank_cust(self, partner_bank_id=False):
        mandate_id = False
        if partner_bank_id:
            partner_bank = self.env['res.partner.bank'].browse(partner_bank_id)
            mandate_ids = partner_bank.mandate_ids
            default_mandate = mandate_ids.filtered(
                lambda r: r.default and r.state == "valid")
            if not default_mandate:
                default_mandate = mandate_ids.filtered(
                    lambda r: r.state == "valid")
            mandate_id = default_mandate and default_mandate[0] or False
        return {'value': {'mandate_id': mandate_id and mandate_id.id or False}}

    @api.multi
    def onchange_partner_id(self, type, partner_id, date_invoice=False,
                            payment_term=False, partner_bank_id=False,
                            company_id=False):
        result = super(AccountInvoice, self).onchange_partner_id(
            type, partner_id, date_invoice=date_invoice,
            payment_term=payment_term, partner_bank_id=partner_bank_id,
            company_id=company_id)
        if partner_id:
            partner = self.env["res.partner"].browse(partner_id)
            result['value']['attach_picking'] = partner.attach_picking

        return result

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        res = super(AccountInvoice, self).name_search(name, args=args,
                                                      operator=operator,
                                                      limit=limit)
        args = args or []
        recs = self.browse()
        if not res:
            recs = self.search([('invoice_number', operator, name)] + args,
                               limit=limit)
            res = recs.name_get()
        return res

    @api.multi
    @api.depends('invoice_line')
    def _get_picking_ids(self):
        for invoice in self:
            invoice.picking_ids = invoice. \
                mapped('invoice_line.move_id.picking_id').sorted()

    @api.multi
    @api.returns('account.move.line')
    def _get_payment(self):
        self.ensure_one()
        payments = self.env['account.move.line'].browse()
        if self.type == "out_invoice" and self.sale_order_ids:
            for sale in self.sale_order_ids:
                payments += sale.payment_ids
        return payments

    @api.multi
    def _can_be_reconciled(self):
        self.ensure_one()
        payments = self._get_payment()
        if not (payments and self.move_id):
            return False
        # Check currency
        company_currency = self.company_id.currency_id
        for payment in payments:
            currency = payment.currency_id or company_currency
            if currency != self.currency_id:
                return False
        return True

    @api.model
    def _get_sum_move_line(self, move_lines, line_type):
        res = {
            'max_date': False,
            'lines': self.env['account.move.line'].browse(),
            'total_amount': 0,
            'total_amount_currency': 0,
        }
        for move_line in move_lines:
            if move_line[line_type] > 0 and not move_line.reconcile_id:
                if move_line.date > res['max_date']:
                    res['max_date'] = move_line.date
                res['lines'] += move_line
                res['total_amount'] += move_line[line_type]
                res['total_amount_currency'] += move_line.amount_currency
        return res

    @api.model
    def _get_sum_invoice_move_line(self, move_lines, invoice_type):
        if invoice_type in ['in_refund', 'out_invoice']:
            line_type = 'debit'
        else:
            line_type = 'credit'
        return self._get_sum_move_line(move_lines, line_type)

    @api.model
    def _get_sum_payment_move_line(self, move_lines, invoice_type):
        if invoice_type in ['in_refund', 'out_invoice']:
            line_type = 'credit'
        else:
            line_type = 'debit'
        return self._get_sum_move_line(move_lines, line_type)

    @api.multi
    def _lines_can_be_reconciled(self, lines):
        self.ensure_one()
        if not lines:
            return False
        # Check that all partners and accounts are the same
        first_partner = lines[0].partner_id
        first_account = lines[0].account_id
        for line in lines:
            if (line.account_id.type in ('receivable', 'payable') and
                        line.partner_id != first_partner):
                return False
            if line.account_id != first_account:
                return False
        return True

    @api.multi
    def _prepare_write_off(self, res_invoice, res_payment):
        self.ensure_one()
        if res_invoice['total_amount'] - res_payment['total_amount'] > 0:
            writeoff_type = 'expense'
        else:
            writeoff_type = 'income'
        writeoff_info = self.company_id.get_write_off_information
        account_id, journal_id = writeoff_info('exchange', writeoff_type)
        max_date = max(res_invoice['max_date'], res_payment['max_date'])
        ctx_vals = {'p_date': max_date}
        period_model = self.env['account.period'].with_context(**ctx_vals)
        period = period_model.find(max_date)[0]
        return {
            'type': 'auto',
            'writeoff_acc_id': account_id,
            'writeoff_period_id': period.id,
            'writeoff_journal_id': journal_id,
            'context_vals': ctx_vals,
        }

    @api.multi
    def _reconcile_invoice(self):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        currency = self.currency_id
        use_currency = currency != company_currency
        if self._can_be_reconciled():
            payment_move_lines = self._get_payment()
            res_payment = self._get_sum_payment_move_line(payment_move_lines,
                                                          self.type)
            res_invoice = self._get_sum_invoice_move_line(self.move_id.line_id,
                                                          self.type)
            lines = res_invoice['lines'] + res_payment['lines']
            if not self._lines_can_be_reconciled(lines):
                return
            if not use_currency:
                balance = abs(res_invoice['total_amount'] -
                              res_payment['total_amount'])
                if lines and currency.is_zero(balance):
                    lines.reconcile()
            else:
                balance = abs(res_invoice['total_amount_currency'] -
                              res_payment['total_amount_currency'])
                if lines and currency.is_zero(balance):
                    kwargs = self._prepare_write_off(res_invoice, res_payment)
                    ctx_vals = kwargs.pop('context_vals')
                    lines.with_context(**ctx_vals).reconcile(**kwargs)

    @api.multi
    def action_move_create(self):
        res = super(AccountInvoice, self).action_move_create()
        for inv in self:
            inv.move_id.line_id.write({'blocked': inv.payment_mode_id.blocked})
            inv._reconcile_invoice()
        return res

    @api.multi
    def write(self, vals):
        res = super(AccountInvoice, self).write(vals)
        for inv in self:
            inv.move_id.line_id.write({'blocked': inv.payment_mode_id.blocked})
        return res


class AccountJournal(models.Model):

    _inherit = "account.journal"

    payment_method_ids = fields.One2many("payment.method", "journal_id",
                                         "Payment methods related",
                                         readonly=True)


class PaymentMode(models.Model):

    _inherit = 'payment.mode'

    blocked = fields.Boolean('No Follow-up')
