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
        'res.currency',
        string='Divisa',
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get('sale_order_id') or self.env.context.get('default_sale_order_id')
        if order_id:
            order = self.env['sale.order'].browse(order_id)
            if order.exists():
                res.setdefault('currency_id', order.currency_id.id)
        return res
    name = fields.Char(
        string='Descripción',
        default=lambda self: _('Comprobante de pago'),
        required=True,
    )
    # No es obligatorio para Efectivo (ahí se genera el recibo automáticamente).
    file = fields.Binary(string='Archivo')
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
    # Solo aplica a Efectivo: firma/sello que se imprime en el recibo.
    signature = fields.Binary(string='Firma / Sello (efectivo)')
    signature_name = fields.Char(string='Nombre del Firmante')
    is_cash = fields.Boolean(
        string='Es Efectivo',
        compute='_compute_is_cash',
    )

    @api.depends('payment_method')
    def _compute_is_cash(self):
        for wiz in self:
            wiz.is_cash = wiz.payment_method == 'cash'

    def _cash_notes(self):
        """Concentra descripción/referencia/notas para el recibo de efectivo."""
        self.ensure_one()
        parts = []
        if self.name and self.name != _('Comprobante de pago'):
            parts.append(self.name)
        if self.reference:
            parts.append(_('Ref.: %s') % self.reference)
        if self.notes:
            parts.append(self.notes)
        return '\n'.join(parts) or False

    def action_confirm(self):
        self.ensure_one()

        # Pago en EFECTIVO: si el módulo de recibos está instalado, se genera el
        # Recibo de Efectivo automáticamente (con su PDF). El recibo, al
        # entregarse, dispara los avisos (Clara aplica / Lourdes factura) y el
        # recordatorio al cajero. No se pide archivo.
        if self.payment_method == 'cash' and 'cash.receipt' in self.env:
            receipt = self.env['cash.receipt'].create({
                'partner_id': self.sale_order_id.partner_id.id,
                'sale_order_ids': [(6, 0, self.sale_order_id.ids)],
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'notes': self._cash_notes(),
                'signature': self.signature,
                'signature_name': self.signature_name,
            })
            receipt.action_deliver()
            if self.add_another:
                return self.sale_order_id.action_open_payment_proof_wizard()
            # Abre/imprime el recibo recién generado para descargarlo.
            return receipt.action_print_receipt()

        # Resto de métodos: comprobante con archivo (obligatorio).
        if not self.file:
            raise UserError(_('Debes adjuntar el comprobante del pago.'))
        self.env['sale.payment.proof'].create(
            {
                'sale_order_id': self.sale_order_id.id,
                'name': self.name or _('Comprobante'),
                'file': self.file,
                'file_name': self.file_name or self.name,
                'amount': self.amount,
                'currency_id': self.currency_id.id,
                'payment_date': self.payment_date,
                'payment_method': self.payment_method,
                'reference': self.reference,
                'notes': self.notes,
            }
        )
        if self.add_another:
            return self.sale_order_id.action_open_payment_proof_wizard()
        return {'type': 'ir.actions.act_window_close'}
