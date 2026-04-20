# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_proof_ids = fields.One2many(
        'sale.payment.proof',
        'sale_order_id',
        string='Comprobantes de Pago',
    )
    payment_proof_count = fields.Integer(
        string='Comprobantes',
        compute='_compute_payment_proof_summary',
    )
    payment_proof_total = fields.Monetary(
        string='Total comprobado',
        compute='_compute_payment_proof_summary',
        currency_field='currency_id',
    )
    payment_proof_pending_count = fields.Integer(
        string='Pendientes',
        compute='_compute_payment_proof_summary',
    )

    @api.depends(
        'payment_proof_ids',
        'payment_proof_ids.amount',
        'payment_proof_ids.state',
    )
    def _compute_payment_proof_summary(self):
        for order in self:
            proofs = order.payment_proof_ids
            order.payment_proof_count = len(proofs)
            order.payment_proof_total = sum(proofs.mapped('amount'))
            order.payment_proof_pending_count = len(
                proofs.filtered(lambda p: p.state == 'pending')
            )

    def action_open_payment_proof_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subir comprobante de pago'),
            'res_model': 'sale.payment.proof.upload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }
