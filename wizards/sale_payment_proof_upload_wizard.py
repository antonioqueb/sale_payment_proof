# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalePaymentProofUploadWizard(models.TransientModel):
    _name = 'sale.payment.proof.upload.wizard'
    _description = 'Asistente para subir comprobantes de pago'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Cliente',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        readonly=True,
    )
    name = fields.Char(
        string='Descripción',
        default=lambda self: _('Comprobante de pago'),
        required=True,
    )
    file = fields.Binary(string='Archivo', required=True)
    file_name = fields.Char(string='Nombre del archivo')
    amount = fields.Monetary(
        string='Monto',
        currency_field='currency_id',
    )
    payment_date = fields.Date(
        string='Fecha del pago',
        default=fields.Date.context_today,
    )
    payment_method = fields.Selection(
        [
            ('transfer', 'Transferencia'),
            ('deposit', 'Depósito'),
            ('cash', 'Efectivo'),
            ('check', 'Cheque'),
            ('card', 'Tarjeta'),
            ('other', 'Otro'),
        ],
        string='Método de pago',
        default='transfer',
    )
    reference = fields.Char(string='Referencia / No. de operación')
    notes = fields.Text(string='Notas')
    add_another = fields.Boolean(
        string='Subir otro comprobante después de guardar',
        default=False,
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_('Debes adjuntar un archivo.'))
        proof = self.env['sale.payment.proof'].create(
            {
                'sale_order_id': self.sale_order_id.id,
                'name': self.name or _('Comprobante'),
                'file': self.file,
                'file_name': self.file_name or self.name,
                'amount': self.amount,
                'payment_date': self.payment_date,
                'payment_method': self.payment_method,
                'reference': self.reference,
                'notes': self.notes,
            }
        )
        if self.add_another:
            return self.sale_order_id.action_open_payment_proof_wizard()
        return {'type': 'ir.actions.act_window_close'}
